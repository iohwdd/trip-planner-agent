from __future__ import annotations

from planner.integrations.qwen import QwenPlannerClient
from planner.services.assistant_store import AssistantConversationStore
from planner.services.knowledge_base_service import knowledge_base_service
from planner.services.request_identity import ActorContext
from planner.services.runtime_config import load_runtime_config


class AssistantService:
    def __init__(self) -> None:
        self.config = load_runtime_config()
        self.store = AssistantConversationStore()
        self.model_client = QwenPlannerClient(self.config.qwen)

    def create_conversation(self, *, actor: ActorContext) -> dict:
        return self.store.create(user=actor.user, guest_token=actor.guest_token)

    def list_conversations(self, *, actor: ActorContext) -> list[dict]:
        return self.store.list(user=actor.user, guest_token=actor.guest_token)

    def get_recent_conversation(self, *, actor: ActorContext) -> dict | None:
        return self.store.get_recent(user=actor.user, guest_token=actor.guest_token)

    def get_conversation(self, conversation_id: str, *, actor: ActorContext) -> dict | None:
        return self.store.get(
            conversation_id,
            user=actor.user,
            guest_token=actor.guest_token,
        )

    def rename_conversation(
        self, conversation_id: str, title: str, *, actor: ActorContext
    ) -> dict:
        return self.store.rename(
            conversation_id,
            title,
            user=actor.user,
            guest_token=actor.guest_token,
        )

    def delete_conversation(self, conversation_id: str, *, actor: ActorContext) -> bool:
        return self.store.delete(
            conversation_id,
            user=actor.user,
            guest_token=actor.guest_token,
        )

    def build_reply(self, conversation_id: str, message: str, *, actor: ActorContext) -> str:
        conversation = self.store.get(
            conversation_id,
            user=actor.user,
            guest_token=actor.guest_token,
        )
        if conversation is None:
            raise KeyError(f"Assistant conversation {conversation_id} not found.")
        assistant_reply = self.model_client.generate_assistant_reply(
            conversation_messages=conversation.get("messages", []),
            latest_user_message=message,
            knowledge_context=self._knowledge_context(message),
        )
        return assistant_reply

    def stream_reply_chunks(self, conversation_id: str, message: str, *, actor: ActorContext):
        conversation = self.store.get(
            conversation_id,
            user=actor.user,
            guest_token=actor.guest_token,
        )
        if conversation is None:
            raise KeyError(f"Assistant conversation {conversation_id} not found.")
        yield from self.model_client.stream_assistant_reply(
            conversation_messages=conversation.get("messages", []),
            latest_user_message=message,
            knowledge_context=self._knowledge_context(message),
        )

    def append_message_reply(self, conversation_id: str, message: str, assistant_reply: str, *, actor: ActorContext) -> dict:
        return self.store.append_exchange(
            conversation_id,
            user_message=message,
            assistant_reply=assistant_reply,
            user=actor.user,
            guest_token=actor.guest_token,
        )

    def send_message(self, conversation_id: str, message: str, *, actor: ActorContext) -> dict:
        assistant_reply = self.build_reply(conversation_id, message, actor=actor)
        return self.append_message_reply(
            conversation_id,
            message,
            assistant_reply,
            actor=actor,
        )

    def summary(self, *, actor: ActorContext) -> dict:
        return self.store.summary(user=actor.user, guest_token=actor.guest_token)

    @staticmethod
    def _knowledge_context(message: str) -> list[dict[str, str]]:
        try:
            chunks = knowledge_base_service.retrieve(message)
            return [
                {
                    "title": item.title,
                    "heading_path": item.heading_path,
                    "content": item.content,
                }
                for item in chunks
            ]
        except Exception:
            return []


assistant_service = AssistantService()
