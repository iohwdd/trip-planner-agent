from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone as django_timezone

from planner.domain.schemas import ChatMessage
from planner.models import AssistantConversationRecord, AssistantMessageRecord

User = get_user_model()


def _is_missing_table_error(error: Exception) -> bool:
    message = str(error).lower()
    return "doesn't exist" in message or "no such table" in message


def _message_to_domain(record: AssistantMessageRecord) -> ChatMessage:
    return ChatMessage(
        message_id=record.message_id,
        role=record.role,  # type: ignore[arg-type]
        content=record.content,
        message_type="text",
        created_at=record.created_at,
    )


class AssistantConversationStore:
    def create(
        self,
        *,
        user: User | None = None,
        guest_token: str | None = None,
        title: str = "未命名助手会话",
    ) -> dict:
        record = AssistantConversationRecord.objects.create(
            owner=user,
            guest_token=None if user else guest_token,
            title=title,
        )
        return self._record_to_payload(record, include_messages=True)

    def list(
        self,
        *,
        user: User | None = None,
        guest_token: str | None = None,
        limit: int = 30,
    ) -> list[dict]:
        return [
            {
                "conversation_id": record.conversation_id,
                "title": record.title,
                "latest_summary": record.latest_summary,
                "message_count": record.message_records.count(),
                "last_accessed_at": record.last_accessed_at,
                "updated_at": record.updated_at,
                "created_at": record.created_at,
            }
            for record in self._scope(user=user, guest_token=guest_token)[:limit]
        ]

    def get(
        self,
        conversation_id: str,
        *,
        user: User | None = None,
        guest_token: str | None = None,
    ) -> dict | None:
        record = self._scope(user=user, guest_token=guest_token).filter(
            conversation_id=conversation_id
        ).prefetch_related("message_records").first()
        if record is None:
            return None
        record.last_accessed_at = django_timezone.now()
        record.touch()
        record.save(update_fields=["last_accessed_at", "updated_at"])
        return self._record_to_payload(record, include_messages=True)

    def get_recent(
        self,
        *,
        user: User | None = None,
        guest_token: str | None = None,
    ) -> dict | None:
        record = self._scope(user=user, guest_token=guest_token).first()
        if record is None:
            return None
        return self.get(record.conversation_id, user=user, guest_token=guest_token)

    def rename(
        self,
        conversation_id: str,
        title: str,
        *,
        user: User | None = None,
        guest_token: str | None = None,
    ) -> dict:
        with transaction.atomic():
            record = self._require_conversation(
                conversation_id, user=user, guest_token=guest_token, lock=True
            )
            record.title = title.strip()[:120] or record.title
            record.last_accessed_at = django_timezone.now()
            record.touch()
            record.save(update_fields=["title", "last_accessed_at", "updated_at"])
        return self.get(conversation_id, user=user, guest_token=guest_token) or {}

    def delete(
        self,
        conversation_id: str,
        *,
        user: User | None = None,
        guest_token: str | None = None,
    ) -> bool:
        deleted, _ = self._scope(user=user, guest_token=guest_token).filter(
            conversation_id=conversation_id
        ).delete()
        return deleted > 0

    def append_exchange(
        self,
        conversation_id: str,
        *,
        user_message: str,
        assistant_reply: str,
        user: User | None = None,
        guest_token: str | None = None,
    ) -> dict:
        with transaction.atomic():
            record = self._require_conversation(
                conversation_id, user=user, guest_token=guest_token, lock=True
            )
            AssistantMessageRecord.objects.create(
                conversation=record,
                role="user",
                content=user_message,
            )
            AssistantMessageRecord.objects.create(
                conversation=record,
                role="assistant",
                content=assistant_reply,
            )
            if record.title == "未命名助手会话":
                record.title = user_message[:40] or record.title
            record.latest_summary = assistant_reply[:200]
            record.last_accessed_at = django_timezone.now()
            record.touch()
            record.save(
                update_fields=["title", "latest_summary", "last_accessed_at", "updated_at"]
            )
        return self.get(conversation_id, user=user, guest_token=guest_token) or {}

    def summary(
        self,
        *,
        user: User | None = None,
        guest_token: str | None = None,
    ) -> dict:
        try:
            query = self._scope(user=user, guest_token=guest_token)
            return {
                "count": query.count(),
                "recent_conversation_id": query.values_list("conversation_id", flat=True).first(),
            }
        except (ProgrammingError, OperationalError) as error:
            if not _is_missing_table_error(error):
                raise
            return {
                "count": 0,
                "recent_conversation_id": None,
            }

    def claim_guest_assets(self, guest_token: str, user: User) -> int:
        try:
            return AssistantConversationRecord.objects.filter(
                guest_token=guest_token,
                owner__isnull=True,
            ).update(
                owner=user,
                guest_token=None,
                updated_at=django_timezone.now(),
                last_accessed_at=django_timezone.now(),
            )
        except (ProgrammingError, OperationalError) as error:
            if not _is_missing_table_error(error):
                raise
            return 0

    def _scope(self, *, user: User | None = None, guest_token: str | None = None):
        if user is not None:
            return AssistantConversationRecord.objects.filter(owner=user).order_by(
                "-last_accessed_at", "-updated_at"
            )
        if guest_token:
            return AssistantConversationRecord.objects.filter(
                guest_token=guest_token,
                owner__isnull=True,
            ).order_by("-last_accessed_at", "-updated_at")
        return AssistantConversationRecord.objects.none()

    def _require_conversation(
        self,
        conversation_id: str,
        *,
        user: User | None = None,
        guest_token: str | None = None,
        lock: bool = False,
    ) -> AssistantConversationRecord:
        query = self._scope(user=user, guest_token=guest_token)
        if lock:
            query = query.select_for_update()
        record = query.filter(conversation_id=conversation_id).first()
        if record is None:
            raise KeyError(f"Assistant conversation {conversation_id} not found.")
        return record

    @staticmethod
    def _record_to_payload(
        record: AssistantConversationRecord,
        *,
        include_messages: bool = False,
    ) -> dict:
        payload = {
            "conversation_id": record.conversation_id,
            "title": record.title,
            "latest_summary": record.latest_summary,
            "message_count": record.message_records.count(),
            "last_accessed_at": record.last_accessed_at,
            "updated_at": record.updated_at,
            "created_at": record.created_at,
        }
        if include_messages:
            payload["messages"] = [
                _message_to_domain(message).model_dump(mode="json")
                for message in record.message_records.order_by("created_at")
            ]
        return payload
