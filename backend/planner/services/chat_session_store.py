from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.utils import timezone as django_timezone

from planner.domain.schemas import (
    ChatSession,
    ChatTurn,
    ChatTurnCreateRequest,
    ConfirmedConstraints,
    ExecutionStep,
    TripPlanOutput,
)
from planner.models import ChatSessionRecord, ChatTurnRecord, generate_hex_id
from planner.services.persistence import (
    model_to_json,
    session_record_to_domain,
    session_summary_dict,
    turn_record_to_domain,
)
from planner.services.planning_context import build_user_message, render_request_summary

User = get_user_model()


class ChatSessionStore:
    def create(
        self,
        *,
        user: User | None = None,
        guest_token: str | None = None,
        title: str = "未命名会话",
        confirmed_constraints: ConfirmedConstraints | None = None,
        latest_result: TripPlanOutput | None = None,
    ) -> ChatSession:
        record = ChatSessionRecord.objects.create(
            owner=user,
            guest_token=None if user else guest_token,
            title=title,
            confirmed_constraints=model_to_json(
                confirmed_constraints or ConfirmedConstraints()
            ),
            latest_result=model_to_json(latest_result),
            latest_summary=(latest_result.trip_summary[:200] if latest_result else ""),
        )
        return session_record_to_domain(record, [])

    def list(
        self,
        *,
        user: User | None = None,
        guest_token: str | None = None,
        limit: int = 30,
    ) -> list[dict]:
        return [
            session_summary_dict(record)
            for record in self._scope(user=user, guest_token=guest_token)[:limit]
        ]

    def get(
        self,
        session_id: str,
        *,
        user: User | None = None,
        guest_token: str | None = None,
        enforce_actor: bool = True,
    ) -> ChatSession | None:
        query = (
            self._scope(user=user, guest_token=guest_token)
            if enforce_actor
            else ChatSessionRecord.objects.all()
        )
        record = (
            query.filter(session_id=session_id)
            .prefetch_related("turn_records")
            .first()
        )
        if record is None:
            return None
        record.last_accessed_at = django_timezone.now()
        record.touch()
        record.save(update_fields=["last_accessed_at", "updated_at"])
        turns = list(record.turn_records.all().order_by("created_at"))
        return session_record_to_domain(record, turns)

    def get_recent(
        self,
        *,
        user: User | None = None,
        guest_token: str | None = None,
    ) -> ChatSession | None:
        record = (
            self._scope(user=user, guest_token=guest_token)
            .prefetch_related("turn_records")
            .order_by("-last_accessed_at", "-updated_at")
            .first()
        )
        if record is None:
            return None
        turns = list(record.turn_records.all().order_by("created_at"))
        return session_record_to_domain(record, turns)

    def create_turn(
        self,
        session_id: str,
        payload: ChatTurnCreateRequest,
        *,
        user: User | None = None,
        guest_token: str | None = None,
    ) -> ChatTurn:
        with transaction.atomic():
            session = self._require_session(
                session_id,
                user=user,
                guest_token=guest_token,
                lock=True,
            )
            if session.active_turn_id and session.status == ChatSessionRecord.STATUS_RUNNING:
                raise RuntimeError("Another chat turn is still running.")

            turn_id = generate_hex_id()
            content = payload.message or render_request_summary(payload.request)
            user_message = build_user_message(message=content, turn_id=turn_id)
            turn = ChatTurnRecord.objects.create(
                turn_id=turn_id,
                session=session,
                status=ChatTurnRecord.STATUS_QUEUED,
                input_mode="form" if payload.request is not None else "chat",
                user_message=model_to_json(user_message),
                request_payload=model_to_json(payload.request),
                confirmed_constraints=session.confirmed_constraints,
            )
            session.active_turn_id = turn_id
            session.status = ChatSessionRecord.STATUS_RUNNING
            session.last_accessed_at = django_timezone.now()
            if session.title == "未命名会话":
                session.title = (content or "未命名会话")[:40]
            session.touch()
            session.save(
                update_fields=[
                    "active_turn_id",
                    "status",
                    "title",
                    "last_accessed_at",
                    "updated_at",
                ]
            )
            return turn_record_to_domain(turn)

    def mark_turn_running(self, session_id: str, turn_id: str) -> None:
        with transaction.atomic():
            session = self._require_session(session_id, lock=True, enforce_actor=False)
            turn = self._require_turn(session, turn_id)
            turn.status = ChatTurnRecord.STATUS_RUNNING
            turn.updated_at = django_timezone.now()
            turn.save(update_fields=["status", "updated_at"])
            session.status = ChatSessionRecord.STATUS_RUNNING
            session.touch()
            session.save(update_fields=["status", "updated_at"])

    def add_step(self, session_id: str, turn_id: str, step: ExecutionStep) -> None:
        with transaction.atomic():
            session = self._require_session(session_id, lock=True, enforce_actor=False)
            turn = self._require_turn(session, turn_id)
            turn.steps = [*turn.steps, model_to_json(step)]
            turn.updated_at = django_timezone.now()
            turn.save(update_fields=["steps", "updated_at"])
            session.touch()
            session.save(update_fields=["updated_at"])

    def complete_turn(
        self,
        session_id: str,
        turn_id: str,
        *,
        result: TripPlanOutput,
        confirmed_constraints: ConfirmedConstraints,
        assistant_message,
    ) -> None:
        with transaction.atomic():
            session = self._require_session(session_id, lock=True, enforce_actor=False)
            turn = self._require_turn(session, turn_id)
            turn.status = ChatTurnRecord.STATUS_COMPLETED
            turn.result_payload = model_to_json(result)
            turn.confirmed_constraints = model_to_json(confirmed_constraints)
            turn.assistant_message = model_to_json(assistant_message)
            turn.updated_at = django_timezone.now()
            turn.save(
                update_fields=[
                    "status",
                    "result_payload",
                    "confirmed_constraints",
                    "assistant_message",
                    "updated_at",
                ]
            )

            session.confirmed_constraints = model_to_json(confirmed_constraints)
            session.latest_result = model_to_json(result)
            session.latest_summary = result.trip_summary[:200]
            session.active_turn_id = None
            session.status = (
                ChatSessionRecord.STATUS_WAITING
                if result.status == "clarification"
                else ChatSessionRecord.STATUS_READY
            )
            session.last_accessed_at = django_timezone.now()
            session.touch()
            session.save(
                update_fields=[
                    "confirmed_constraints",
                    "latest_result",
                    "latest_summary",
                    "active_turn_id",
                    "status",
                    "last_accessed_at",
                    "updated_at",
                ]
            )

    def fail_turn(self, session_id: str, turn_id: str, error: str) -> None:
        with transaction.atomic():
            session = self._require_session(session_id, lock=True, enforce_actor=False)
            turn = self._require_turn(session, turn_id)
            turn.status = ChatTurnRecord.STATUS_FAILED
            turn.error = error
            turn.updated_at = django_timezone.now()
            turn.save(update_fields=["status", "error", "updated_at"])
            session.active_turn_id = None
            session.status = ChatSessionRecord.STATUS_FAILED
            session.last_accessed_at = django_timezone.now()
            session.touch()
            session.save(
                update_fields=["active_turn_id", "status", "last_accessed_at", "updated_at"]
            )

    def get_turn(
        self,
        session_id: str,
        turn_id: str,
        *,
        user: User | None = None,
        guest_token: str | None = None,
        enforce_actor: bool = True,
    ) -> ChatTurn | None:
        session = self._require_session(
            session_id,
            user=user,
            guest_token=guest_token,
            enforce_actor=enforce_actor,
        )
        try:
            turn = self._require_turn(session, turn_id)
        except KeyError:
            return None
        return turn_record_to_domain(turn)

    def rename_session(
        self,
        session_id: str,
        title: str,
        *,
        user: User | None = None,
        guest_token: str | None = None,
    ) -> ChatSession:
        with transaction.atomic():
            session = self._require_session(
                session_id, user=user, guest_token=guest_token, lock=True
            )
            session.title = title.strip()[:120] or session.title
            session.last_accessed_at = django_timezone.now()
            session.touch()
            session.save(update_fields=["title", "last_accessed_at", "updated_at"])
            return self.get(
                session_id, user=user, guest_token=guest_token
            ) or session_record_to_domain(session)

    def delete_session(
        self,
        session_id: str,
        *,
        user: User | None = None,
        guest_token: str | None = None,
    ) -> bool:
        query = self._scope(user=user, guest_token=guest_token)
        deleted, _ = query.filter(session_id=session_id).delete()
        return deleted > 0

    def claim_guest_assets(self, guest_token: str, user: User) -> int:
        return ChatSessionRecord.objects.filter(
            guest_token=guest_token, owner__isnull=True
        ).update(
            owner=user,
            guest_token=None,
            updated_at=django_timezone.now(),
            last_accessed_at=django_timezone.now(),
        )

    def create_from_plan(
        self,
        *,
        user: User,
        title: str,
        confirmed_constraints: ConfirmedConstraints,
        latest_result: TripPlanOutput | None,
    ) -> ChatSession:
        return self.create(
            user=user,
            title=title,
            confirmed_constraints=confirmed_constraints,
            latest_result=latest_result,
        )

    def summary(
        self,
        *,
        user: User | None = None,
        guest_token: str | None = None,
    ) -> dict:
        query = self._scope(user=user, guest_token=guest_token)
        status_counts = {
            row["status"]: row["count"]
            for row in query.values("status").annotate(count=Count("session_id"))
        }
        recent = query.order_by("-last_accessed_at", "-updated_at").first()
        return {
            "count": query.count(),
            "status_counts": status_counts,
            "recent_session_id": recent.session_id if recent is not None else None,
        }

    def _scope(
        self,
        *,
        user: User | None = None,
        guest_token: str | None = None,
    ):
        query = ChatSessionRecord.objects.all().order_by("-updated_at")
        if user and getattr(user, "is_authenticated", False):
            return query.filter(owner=user)
        if guest_token:
            return query.filter(owner__isnull=True, guest_token=guest_token)
        return query.none()

    def _require_session(
        self,
        session_id: str,
        *,
        user: User | None = None,
        guest_token: str | None = None,
        lock: bool = False,
        enforce_actor: bool = True,
    ) -> ChatSessionRecord:
        query = (
            self._scope(user=user, guest_token=guest_token)
            if enforce_actor
            else ChatSessionRecord.objects.all()
        )
        if lock:
            query = query.select_for_update()
        session = query.filter(session_id=session_id).first()
        if session is None:
            raise KeyError(f"Chat session {session_id} not found.")
        return session

    @staticmethod
    def _require_turn(session: ChatSessionRecord, turn_id: str) -> ChatTurnRecord:
        turn = session.turn_records.filter(turn_id=turn_id).first()
        if turn is None:
            raise KeyError(f"Chat turn {turn_id} not found.")
        return turn
