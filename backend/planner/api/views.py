from __future__ import annotations

import json
import threading
import time
from typing import Literal

from django.conf import settings
from django.http import StreamingHttpResponse
from django.db.utils import OperationalError, ProgrammingError
from pydantic import BaseModel, ValidationError, field_validator
from rest_framework import status as drf_status
from rest_framework.decorators import api_view
from rest_framework.decorators import renderer_classes
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response

from planner.domain.schemas import ChatTurn, ChatTurnCreateRequest, TripPlanningRequest
from planner.services.assistant_service import assistant_service
from planner.services.auth_service import (
    AuthDeliveryError,
    AuthRateLimitError,
    AuthValidationError,
    auth_service,
)
from planner.services.knowledge_base_service import knowledge_base_service
from planner.services.planner_service import planner_service
from planner.services.request_identity import (
    create_guest_token,
    get_actor_context,
)


class AuthCodeRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email:
            raise ValueError("请输入合法的邮箱地址。")
        return email


class AuthVerifyRequest(BaseModel):
    email: str
    code: str
    guest_token: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email:
            raise ValueError("请输入合法的邮箱地址。")
        return email

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        code = value.strip()
        if not code:
            raise ValueError("验证码不能为空。")
        return code


class PasswordLoginRequest(BaseModel):
    email: str
    password: str
    guest_token: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email:
            raise ValueError("请输入合法的邮箱地址。")
        return email

    @field_validator("password")
    @classmethod
    def ensure_password_present(cls, value: str) -> str:
        password = value.strip()
        if not password:
            raise ValueError("密码不能为空。")
        return password


class ServerSentEventRenderer(BaseRenderer):
    media_type = "text/event-stream"
    format = "event-stream"
    charset = "utf-8"
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return b""
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            return data.encode(self.charset)
        return json.dumps(data, ensure_ascii=False).encode(self.charset)


class PasswordChangeRequest(BaseModel):
    current_password: str | None = None
    new_password: str

    @field_validator("current_password")
    @classmethod
    def normalize_current_password(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("new_password")
    @classmethod
    def ensure_new_password_present(cls, value: str) -> str:
        password = value.strip()
        if not password:
            raise ValueError("新密码不能为空。")
        return password


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class SessionRenameRequest(BaseModel):
    title: str

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("会话标题不能为空。")
        return title[:120]


class SaveTripPlanRequest(BaseModel):
    status: Literal["draft", "final"] = "draft"
    title: str | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        title = value.strip()
        return title[:160] or None


class AssistantMessageCreateRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        message = value.strip()
        if not message:
            raise ValueError("消息不能为空。")
        return message


def _require_staff_actor(request):
    actor = get_actor_context(request)
    if not actor.user:
        return actor, _error_response(
            "请先登录后访问知识库。",
            code="auth_required",
            status_code=drf_status.HTTP_401_UNAUTHORIZED,
        )
    if not actor.user.is_staff:
        return actor, _error_response(
            "当前账号无权访问知识库。",
            code="knowledge_forbidden",
            status_code=drf_status.HTTP_403_FORBIDDEN,
        )
    return actor, None


def _parse_json_payload(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}"), None
    except json.JSONDecodeError:
        return None, Response(
            {"error": "请求体不是合法的 JSON。"},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )


def _validation_error(exc: ValidationError, message: str):
    return Response(
        {"error": message, "code": "validation_error", "source": "api", "details": exc.errors()},
        status=drf_status.HTTP_400_BAD_REQUEST,
    )


def _error_response(message: str, *, code: str, status_code: int, details=None):
    payload = {
        "error": message,
        "code": code,
        "source": "api",
    }
    if details is not None:
        payload["details"] = details
    return Response(payload, status=status_code)


def _knowledge_service_error_response(exc: Exception):
    if isinstance(exc, (ProgrammingError, OperationalError)):
        return _error_response(
            "知识库数据表或字段尚未完成迁移，请先执行后端数据库迁移。",
            code="knowledge_schema_outdated",
            status_code=drf_status.HTTP_503_SERVICE_UNAVAILABLE,
            details={
                "hint": "cd backend && .venv/bin/python manage.py migrate",
                "reason": str(exc),
            },
        )
    return _error_response(
        str(exc) or "知识库服务暂时不可用。",
        code="knowledge_service_unavailable",
        status_code=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _client_ip(request) -> str:
    return request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get(
        "REMOTE_ADDR", ""
    )


def _turn_phase(turn: ChatTurn) -> str:
    if turn.status in {"queued", "running", "failed"}:
        return turn.status
    if turn.result is None:
        return "completed" if turn.status == "completed" else turn.status
    if turn.result.status == "clarification":
        return "clarification"
    if turn.result.status == "failed":
        return "failed"
    return "completed"


def _serialize_turn(turn: ChatTurn) -> dict:
    payload = turn.model_dump(mode="json")
    payload["phase"] = _turn_phase(turn)
    payload["stream_supported"] = True
    payload["result_partial"] = bool(turn.result and turn.result.status == "clarification")
    return payload


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _split_message_chunks(content: str) -> list[str]:
    if not content:
        return []
    chunks: list[str] = []
    current = ""
    delimiters = "。！？!?；;\n"
    for char in content:
        current += char
        if char in delimiters or len(current) >= 38:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


def _stream_chat_turn_events(*, session_id: str, turn: ChatTurn, actor, guest_token: str | None):
    last_status = ""
    last_phase = ""
    last_result_signature = ""
    emitted_message = False
    seen_steps: dict[str, str] = {}
    started_at = time.monotonic()

    yield _sse(
        "turn.created",
        {
            "session_id": session_id,
            "turn_id": turn.turn_id,
            "status": turn.status,
            "phase": _turn_phase(turn),
            "status_url": f"/api/chat/sessions/{session_id}/turns/{turn.turn_id}/",
            "stream_supported": True,
            "guest_token": guest_token,
        },
    )

    while True:
        current_turn = planner_service.get_chat_turn(session_id, turn.turn_id, actor=actor)
        if current_turn is None:
            yield _sse(
                "turn.error",
                {
                    "session_id": session_id,
                    "turn_id": turn.turn_id,
                    "status": "failed",
                    "phase": "failed",
                    "error": "流式会话已失效，请刷新后重试。",
                    "code": "turn_not_found",
                },
            )
            return

        current_phase = _turn_phase(current_turn)
        if current_turn.status != last_status or current_phase != last_phase:
            last_status = current_turn.status
            last_phase = current_phase
            yield _sse(
                "turn.status",
                {
                    "session_id": session_id,
                    "turn_id": current_turn.turn_id,
                    "status": current_turn.status,
                    "phase": current_phase,
                    "session_status": "running" if current_turn.status in {"queued", "running"} else current_phase,
                },
            )

        for step in current_turn.steps:
            serialized_step = json.dumps(step.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            if seen_steps.get(step.key) == serialized_step:
                continue
            seen_steps[step.key] = serialized_step
            yield _sse(
                "turn.step",
                {
                    "session_id": session_id,
                    "turn_id": current_turn.turn_id,
                    "step": step.model_dump(mode="json"),
                },
            )

        if current_turn.result is not None:
            serialized_result = json.dumps(current_turn.result.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            if serialized_result != last_result_signature:
                last_result_signature = serialized_result
                yield _sse(
                    "turn.result",
                    {
                        "session_id": session_id,
                        "turn_id": current_turn.turn_id,
                        "phase": current_phase,
                        "result": current_turn.result.model_dump(mode="json"),
                    },
                )

        if current_turn.status == "completed":
            if current_turn.assistant_message is not None and not emitted_message:
                accumulated = ""
                for chunk in _split_message_chunks(current_turn.assistant_message.content):
                    accumulated += chunk
                    yield _sse(
                        "message.delta",
                        {
                            "session_id": session_id,
                            "turn_id": current_turn.turn_id,
                            "delta": chunk,
                            "content": accumulated,
                            "message_type": current_turn.assistant_message.message_type,
                        },
                    )
                    time.sleep(0.04)
                emitted_message = True
                yield _sse(
                    "message.complete",
                    {
                        "session_id": session_id,
                        "turn_id": current_turn.turn_id,
                        "message": current_turn.assistant_message.model_dump(mode="json"),
                    },
                )

            yield _sse(
                "turn.complete",
                {
                    "session_id": session_id,
                    "turn_id": current_turn.turn_id,
                    "status": current_turn.status,
                    "phase": current_phase,
                    "result": current_turn.result.model_dump(mode="json") if current_turn.result else None,
                },
            )
            return

        if current_turn.status == "failed":
            yield _sse(
                "turn.error",
                {
                    "session_id": session_id,
                    "turn_id": current_turn.turn_id,
                    "status": "failed",
                    "phase": "failed",
                    "error": current_turn.error or "回合执行失败。",
                    "code": "turn_failed",
                },
            )
            return

        if time.monotonic() - started_at > settings.TRIP_PLANNER_JOB_TIMEOUT_SECONDS + 10:
            yield _sse(
                "turn.error",
                {
                    "session_id": session_id,
                    "turn_id": current_turn.turn_id,
                    "status": "failed",
                    "phase": "failed",
                    "error": "流式等待超时，请稍后刷新会话查看最新状态。",
                    "code": "stream_timeout",
                },
            )
            return

        yield ": keep-alive\n\n"
        time.sleep(0.35)


def _stream_assistant_message_events(
    *,
    conversation_id: str,
    message: str,
    actor,
    guest_token: str | None,
):
    yield _sse(
        "message.accepted",
        {
            "conversation_id": conversation_id,
            "status": "running",
            "guest_token": guest_token,
        },
    )

    try:
        accumulated = ""
        for chunk in assistant_service.stream_reply_chunks(
            conversation_id,
            message,
            actor=actor,
        ):
            accumulated += chunk
            yield _sse(
                "message.delta",
                {
                    "conversation_id": conversation_id,
                    "delta": chunk,
                    "content": accumulated,
                    "message_type": "text",
                },
            )
        conversation = assistant_service.append_message_reply(
            conversation_id,
            message,
            accumulated,
            actor=actor,
        )
    except KeyError:
        yield _sse(
            "message.error",
            {
                "conversation_id": conversation_id,
                "status": "failed",
                "error": "未找到对应的助手会话。",
                "code": "assistant_conversation_not_found",
            },
        )
        return
    except Exception as exc:  # pragma: no cover - defensive guard for stream errors
        yield _sse(
            "message.error",
            {
                "conversation_id": conversation_id,
                "status": "failed",
                "error": str(exc) or "助手回复失败。",
                "code": "assistant_message_failed",
            },
        )
        return

    assistant_message = next(
        (
            item
            for item in reversed(conversation.get("messages", []))
            if item.get("role") == "assistant"
        ),
        None,
    )
    if assistant_message is None:
        yield _sse(
            "message.error",
            {
                "conversation_id": conversation_id,
                "status": "failed",
                "error": "助手消息未成功写入。",
                "code": "assistant_message_missing",
            },
        )
        return

    yield _sse(
        "message.complete",
        {
            "conversation_id": conversation_id,
            "message": assistant_message,
            "conversation": conversation,
        },
    )


def _stream_plan_run_events(*, run_id: str, actor, guest_token: str | None):
    last_status = ""
    last_result_signature = ""
    seen_steps: dict[str, str] = {}
    started_at = time.monotonic()

    yield _sse(
        "run.created",
        {
            "run_id": run_id,
            "status": "queued",
            "status_url": f"/api/plans/{run_id}/",
            "guest_token": guest_token,
        },
    )

    while True:
        run = planner_service.get_run(run_id, actor=actor)
        if run is None:
            yield _sse(
                "run.error",
                {
                    "run_id": run_id,
                    "status": "failed",
                    "error": "未找到对应的规划任务。",
                    "code": "plan_run_not_found",
                },
            )
            return

        if run.status != last_status:
            last_status = run.status
            yield _sse(
                "run.status",
                {
                    "run_id": run.run_id,
                    "status": run.status,
                },
            )

        for step in run.steps:
            serialized_step = json.dumps(step.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            if seen_steps.get(step.key) == serialized_step:
                continue
            seen_steps[step.key] = serialized_step
            yield _sse(
                "run.step",
                {
                    "run_id": run.run_id,
                    "step": step.model_dump(mode="json"),
                },
            )

        if run.result is not None:
            serialized_result = json.dumps(run.result.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            if serialized_result != last_result_signature:
                last_result_signature = serialized_result
                yield _sse(
                    "run.result",
                    {
                        "run_id": run.run_id,
                        "result": run.result.model_dump(mode="json"),
                    },
                )

        if run.status == "completed":
            yield _sse(
                "run.complete",
                {
                    "run_id": run.run_id,
                    "status": run.status,
                    "result": run.result.model_dump(mode="json") if run.result else None,
                },
            )
            return

        if run.status == "failed":
            yield _sse(
                "run.error",
                {
                    "run_id": run.run_id,
                    "status": run.status,
                    "error": run.error or "规划执行失败。",
                    "code": "plan_run_failed",
                },
            )
            return

        if time.monotonic() - started_at > settings.TRIP_PLANNER_JOB_TIMEOUT_SECONDS + 10:
            yield _sse(
                "run.error",
                {
                    "run_id": run.run_id,
                    "status": "failed",
                    "error": "规划流式等待超时，请稍后刷新结果。",
                    "code": "stream_timeout",
                },
            )
            return

        yield ": keep-alive\n\n"
        time.sleep(0.2)


@api_view(["GET"])
def health_check(_request):
    return Response({"status": "ok"})


@api_view(["GET", "POST"])
def assistant_conversations_view(request):
    actor = get_actor_context(request)
    if request.method == "GET":
        summary = assistant_service.summary(actor=actor)
        items = assistant_service.list_conversations(actor=actor)
        return Response(
            {
                "items": items,
                "count": summary["count"],
                "recent_conversation_id": summary["recent_conversation_id"],
            }
        )

    if not actor.user and not actor.guest_token:
        actor = actor.__class__(user=None, guest_token=create_guest_token())
    conversation = assistant_service.create_conversation(actor=actor)
    payload = {
        "conversation_id": conversation["conversation_id"],
        "title": conversation["title"],
        "latest_summary": conversation.get("latest_summary", ""),
        "messages": conversation.get("messages", []),
        "message_count": conversation.get("message_count", 0),
        "created_at": conversation.get("created_at"),
        "updated_at": conversation.get("updated_at"),
        "last_accessed_at": conversation.get("last_accessed_at"),
    }
    if actor.guest_token and not actor.user:
        payload["guest_token"] = actor.guest_token
    return Response(payload, status=drf_status.HTTP_201_CREATED)


@api_view(["GET"])
def recent_assistant_conversation_view(request):
    conversation = assistant_service.get_recent_conversation(
        actor=get_actor_context(request)
    )
    if conversation is None:
        return Response(
            {
                "error": "未找到最近助手会话。",
                "code": "assistant_conversation_not_found",
                "source": "api",
            },
            status=drf_status.HTTP_404_NOT_FOUND,
        )
    return Response(conversation)


@api_view(["GET", "PATCH", "DELETE"])
def assistant_conversation_view(request, conversation_id: str):
    actor = get_actor_context(request)
    if request.method == "GET":
        conversation = assistant_service.get_conversation(conversation_id, actor=actor)
        if conversation is None:
            return Response(
                {
                    "error": "未找到对应的助手会话。",
                    "code": "assistant_conversation_not_found",
                    "source": "api",
                },
                status=drf_status.HTTP_404_NOT_FOUND,
            )
        return Response(conversation)

    if request.method == "PATCH":
        payload, error_response = _parse_json_payload(request)
        if error_response is not None:
            return error_response
        try:
            rename_request = SessionRenameRequest.model_validate(payload)
            conversation = assistant_service.rename_conversation(
                conversation_id, rename_request.title, actor=actor
            )
        except ValidationError as exc:
            return _validation_error(exc, "助手会话重命名参数无效。")
        except KeyError:
            return Response(
                {
                    "error": "未找到对应的助手会话。",
                    "code": "assistant_conversation_not_found",
                    "source": "api",
                },
                status=drf_status.HTTP_404_NOT_FOUND,
            )
        return Response(conversation)

    deleted = assistant_service.delete_conversation(conversation_id, actor=actor)
    if not deleted:
        return Response(
            {
                "error": "未找到对应的助手会话。",
                "code": "assistant_conversation_not_found",
                "source": "api",
            },
            status=drf_status.HTTP_404_NOT_FOUND,
        )
    return Response(status=drf_status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
def create_assistant_message_view(request, conversation_id: str):
    payload, error_response = _parse_json_payload(request)
    if error_response is not None:
        return error_response
    try:
        message_request = AssistantMessageCreateRequest.model_validate(payload)
    except ValidationError as exc:
        return _validation_error(exc, "助手消息参数无效。")

    actor = get_actor_context(request)
    try:
        conversation = assistant_service.send_message(
            conversation_id,
            message_request.message,
            actor=actor,
        )
    except KeyError:
        return Response(
            {
                "error": "未找到对应的助手会话。",
                "code": "assistant_conversation_not_found",
                "source": "api",
            },
            status=drf_status.HTTP_404_NOT_FOUND,
        )
    return Response(conversation)


@api_view(["POST"])
@renderer_classes([ServerSentEventRenderer, JSONRenderer])
def create_assistant_message_stream_view(request, conversation_id: str):
    payload, error_response = _parse_json_payload(request)
    if error_response is not None:
        return error_response
    try:
        message_request = AssistantMessageCreateRequest.model_validate(payload)
    except ValidationError as exc:
        return _validation_error(exc, "助手消息参数无效。")

    actor = get_actor_context(request)
    response = StreamingHttpResponse(
        _stream_assistant_message_events(
            conversation_id=conversation_id,
            message=message_request.message,
            actor=actor,
            guest_token=actor.guest_token,
        ),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@api_view(["POST"])
def send_auth_code_view(request):
    payload, error_response = _parse_json_payload(request)
    if error_response is not None:
        return error_response
    try:
        auth_request = AuthCodeRequest.model_validate(payload)
    except ValidationError as exc:
        return _validation_error(exc, "验证码请求参数无效。")
    try:
        result = auth_service.send_login_code(
            email=auth_request.email,
            request_ip=_client_ip(request),
        )
    except AuthRateLimitError as exc:
        return _error_response(str(exc), code="auth_rate_limited", status_code=drf_status.HTTP_429_TOO_MANY_REQUESTS)
    except AuthDeliveryError as exc:
        return _error_response(str(exc), code="auth_delivery_failed", status_code=drf_status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(result, status=drf_status.HTTP_202_ACCEPTED)


@api_view(["POST"])
def verify_auth_code_view(request):
    payload, error_response = _parse_json_payload(request)
    if error_response is not None:
        return error_response
    try:
        auth_request = AuthVerifyRequest.model_validate(payload)
    except ValidationError as exc:
        return _validation_error(exc, "登录校验参数无效。")
    try:
        result = auth_service.verify_login_code(
            email=auth_request.email,
            code=auth_request.code.strip(),
            guest_token=auth_request.guest_token,
        )
    except AuthValidationError as exc:
        return _error_response(str(exc), code="auth_validation_failed", status_code=drf_status.HTTP_400_BAD_REQUEST)
    return Response(result, status=drf_status.HTTP_200_OK)


@api_view(["GET"])
def auth_me_view(request):
    actor = get_actor_context(request)
    summary = planner_service.get_identity_summary(actor=actor)
    if not actor.user:
        return Response(
            {"authenticated": False, **summary},
            status=drf_status.HTTP_200_OK,
        )
    return Response(
        {
            "authenticated": True,
            "user": {
                "id": str(actor.user.pk),
                "email": actor.user.email,
                "display_name": actor.user.display_name,
                "has_password": actor.user.has_usable_password(),
                "is_staff": bool(actor.user.is_staff),
            },
            **summary,
        }
    )


@api_view(["GET"])
def knowledge_dashboard_view(request):
    actor, error_response = _require_staff_actor(request)
    if error_response is not None:
        return error_response
    try:
        payload = knowledge_base_service.get_dashboard_payload(actor=actor.user)
    except Exception as exc:
        return _knowledge_service_error_response(exc)
    return Response(payload)


@api_view(["GET"])
def knowledge_overview_view(request):
    actor, error_response = _require_staff_actor(request)
    if error_response is not None:
        return error_response
    try:
        payload = knowledge_base_service.get_overview_payload(actor=actor.user)
    except Exception as exc:
        return _knowledge_service_error_response(exc)
    return Response(payload)


@api_view(["POST"])
def knowledge_documents_view(request):
    actor, error_response = _require_staff_actor(request)
    if error_response is not None:
        return error_response
    upload = request.FILES.get("file")
    if upload is None:
        return _error_response(
            "请上传文件。",
            code="knowledge_file_required",
            status_code=drf_status.HTTP_400_BAD_REQUEST,
        )
    try:
        document = knowledge_base_service.upload_document(
            file_name=upload.name,
            content_type=getattr(upload, "content_type", "") or "",
            file_bytes=upload.read(),
            actor=actor.user,
        )
    except ValueError as exc:
        return _error_response(
            str(exc),
            code="knowledge_upload_invalid",
            status_code=drf_status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:
        return _knowledge_service_error_response(exc)
    return Response(document, status=drf_status.HTTP_202_ACCEPTED)


@api_view(["DELETE"])
def knowledge_document_view(request, document_id: str):
    _actor, error_response = _require_staff_actor(request)
    if error_response is not None:
        return error_response
    try:
        deleted = knowledge_base_service.delete_document(document_id)
    except Exception as exc:
        return _knowledge_service_error_response(exc)
    if not deleted:
        return _error_response(
            "未找到对应的知识库文档。",
            code="knowledge_document_not_found",
            status_code=drf_status.HTTP_404_NOT_FOUND,
        )
    return Response(status=drf_status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
def knowledge_document_retry_view(request, document_id: str):
    _actor, error_response = _require_staff_actor(request)
    if error_response is not None:
        return error_response
    try:
        document = knowledge_base_service.retry_document(document_id)
    except Exception as exc:
        return _knowledge_service_error_response(exc)
    if document is None:
        return _error_response(
            "未找到对应的知识库文档。",
            code="knowledge_document_not_found",
            status_code=drf_status.HTTP_404_NOT_FOUND,
        )
    return Response(document, status=drf_status.HTTP_202_ACCEPTED)


@api_view(["POST"])
def knowledge_reindex_view(request):
    _actor, error_response = _require_staff_actor(request)
    if error_response is not None:
        return error_response
    try:
        payload = knowledge_base_service.reindex_all()
    except Exception as exc:
        return _knowledge_service_error_response(exc)
    return Response(payload, status=drf_status.HTTP_202_ACCEPTED)


@api_view(["POST"])
def password_login_view(request):
    payload, error_response = _parse_json_payload(request)
    if error_response is not None:
        return error_response
    try:
        login_request = PasswordLoginRequest.model_validate(payload)
    except ValidationError as exc:
        return _validation_error(exc, "密码登录参数无效。")
    try:
        result = auth_service.login_with_password(
            email=login_request.email.strip(),
            password=login_request.password,
            guest_token=login_request.guest_token,
        )
    except AuthValidationError as exc:
        return _error_response(str(exc), code="password_login_failed", status_code=drf_status.HTTP_400_BAD_REQUEST)
    return Response(result, status=drf_status.HTTP_200_OK)


@api_view(["POST"])
def set_password_view(request):
    actor = get_actor_context(request)
    if not actor.user:
        return Response(
            {"error": "请先登录后设置密码。", "code": "auth_required", "source": "api"},
            status=drf_status.HTTP_401_UNAUTHORIZED,
        )
    payload, error_response = _parse_json_payload(request)
    if error_response is not None:
        return error_response
    try:
        password_request = PasswordChangeRequest.model_validate(payload)
    except ValidationError as exc:
        return _validation_error(exc, "密码设置参数无效。")
    try:
        result = auth_service.set_password(
            user=actor.user,
            current_password=password_request.current_password,
            new_password=password_request.new_password,
        )
    except AuthValidationError as exc:
        return _error_response(str(exc), code="password_update_failed", status_code=drf_status.HTTP_400_BAD_REQUEST)
    return Response(result, status=drf_status.HTTP_200_OK)


@api_view(["POST"])
def logout_view(request):
    payload, error_response = _parse_json_payload(request)
    if error_response is not None:
        return error_response
    try:
        logout_request = LogoutRequest.model_validate(payload)
    except ValidationError as exc:
        return _validation_error(exc, "退出登录参数无效。")
    auth_service.logout(refresh_token=logout_request.refresh_token)
    return Response({"message": "已退出登录。"})


@api_view(["POST"])
def plan_trip_view(request):
    payload, error_response = _parse_json_payload(request)
    if error_response is not None:
        return error_response
    try:
        plan_request = TripPlanningRequest.model_validate(payload)
    except ValidationError as exc:
        return _validation_error(exc, "旅行规划请求参数无效。")

    actor = get_actor_context(request)
    if not actor.user and not actor.guest_token:
        actor = actor.__class__(user=None, guest_token=create_guest_token())

    run = planner_service.start_run(plan_request, actor=actor)
    response_payload = {
        "run_id": run.run_id,
        "status": run.status,
        "status_url": f"/api/plans/{run.run_id}/",
    }
    if actor.guest_token and not actor.user:
        response_payload["guest_token"] = actor.guest_token
    return Response(response_payload, status=drf_status.HTTP_202_ACCEPTED)


@api_view(["POST"])
@renderer_classes([ServerSentEventRenderer, JSONRenderer])
def plan_trip_stream_view(request):
    payload, error_response = _parse_json_payload(request)
    if error_response is not None:
        return error_response
    try:
        plan_request = TripPlanningRequest.model_validate(payload)
    except ValidationError as exc:
        return _validation_error(exc, "旅行规划请求参数无效。")

    actor = get_actor_context(request)
    if not actor.user and not actor.guest_token:
        actor = actor.__class__(user=None, guest_token=create_guest_token())

    run = planner_service.create_run(plan_request, actor=actor)
    threading.Thread(
        target=planner_service.execute_job,
        args=(run.run_id,),
        daemon=True,
    ).start()

    response = StreamingHttpResponse(
        _stream_plan_run_events(
            run_id=run.run_id,
            actor=actor,
            guest_token=actor.guest_token,
        ),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@api_view(["GET"])
def plan_status_view(request, run_id: str):
    run = planner_service.get_run(run_id, actor=get_actor_context(request))
    if run is None:
        return Response(
            {"error": "未找到对应的规划任务。", "code": "plan_run_not_found", "source": "api"},
            status=drf_status.HTTP_404_NOT_FOUND,
        )
    return Response(run.model_dump(mode="json"))


@api_view(["POST"])
def save_run_plan_view(request, run_id: str):
    payload, error_response = _parse_json_payload(request)
    if error_response is not None:
        return error_response
    try:
        save_request = SaveTripPlanRequest.model_validate(payload)
    except ValidationError as exc:
        return _validation_error(exc, "方案保存参数无效。")

    try:
        result = planner_service.save_trip_plan_from_run(
            run_id,
            actor=get_actor_context(request),
            status=save_request.status,
            title=save_request.title,
        )
    except PermissionError:
        return Response(
            {"error": "登录后才能保存旅行方案。", "code": "auth_required", "source": "api"},
            status=drf_status.HTTP_401_UNAUTHORIZED,
        )
    except KeyError:
        return Response(
            {"error": "未找到对应的规划运行。", "code": "plan_run_not_found", "source": "api"},
            status=drf_status.HTTP_404_NOT_FOUND,
        )
    except ValueError as exc:
        return Response(
            {"error": str(exc), "code": "plan_run_not_ready", "source": "api"},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )
    return Response(result, status=drf_status.HTTP_201_CREATED)


@api_view(["GET", "POST"])
def chat_sessions_view(request):
    actor = get_actor_context(request)
    if request.method == "GET":
        items = planner_service.list_chat_sessions(actor=actor)
        summary = planner_service.get_chat_session_summary(actor=actor)
        return Response(
            {
                "items": items,
                "count": summary["count"],
                "status_counts": summary["status_counts"],
                "recent_session_id": summary["recent_session_id"],
            }
        )

    if not actor.user and not actor.guest_token:
        actor = actor.__class__(user=None, guest_token=create_guest_token())
    session = planner_service.create_chat_session(actor=actor)
    payload = {
        "session_id": session.session_id,
        "status": session.status,
        "title": session.title,
        "session_url": f"/api/chat/sessions/{session.session_id}/",
    }
    if actor.guest_token and not actor.user:
        payload["guest_token"] = actor.guest_token
    return Response(payload, status=drf_status.HTTP_201_CREATED)


@api_view(["GET"])
def recent_chat_session_view(request):
    session = planner_service.get_recent_chat_session(actor=get_actor_context(request))
    if session is None:
        return Response(
                {"error": "未找到最近会话。", "code": "recent_session_not_found", "source": "api"},
            status=drf_status.HTTP_404_NOT_FOUND,
        )
    return Response(session.model_dump(mode="json"))


@api_view(["GET", "PATCH", "DELETE"])
def chat_session_view(request, session_id: str):
    actor = get_actor_context(request)
    if request.method == "GET":
        session = planner_service.get_chat_session(session_id, actor=actor)
        if session is None:
            return Response(
                {"error": "未找到对应的会话。", "code": "chat_session_not_found", "source": "api"},
                status=drf_status.HTTP_404_NOT_FOUND,
            )
        payload = session.model_dump(mode="json")
        payload["stream_supported"] = True
        return Response(payload)

    if request.method == "PATCH":
        payload, error_response = _parse_json_payload(request)
        if error_response is not None:
            return error_response
        try:
            rename_request = SessionRenameRequest.model_validate(payload)
        except ValidationError as exc:
            return _validation_error(exc, "会话重命名参数无效。")
        try:
            session = planner_service.rename_chat_session(
                session_id, rename_request.title, actor=actor
            )
        except KeyError:
            return Response(
                {"error": "未找到对应的会话。", "code": "chat_session_not_found", "source": "api"},
                status=drf_status.HTTP_404_NOT_FOUND,
            )
        return Response(session.model_dump(mode="json"))

    deleted = planner_service.delete_chat_session(session_id, actor=actor)
    if not deleted:
        return Response(
            {"error": "未找到对应的会话。", "code": "chat_session_not_found", "source": "api"},
            status=drf_status.HTTP_404_NOT_FOUND,
        )
    return Response(status=drf_status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
def create_chat_turn_view(request, session_id: str):
    payload, error_response = _parse_json_payload(request)
    if error_response is not None:
        return error_response
    try:
        turn_request = ChatTurnCreateRequest.model_validate(payload)
    except ValidationError as exc:
        return _validation_error(exc, "聊天回合参数无效。")

    actor = get_actor_context(request)
    try:
        turn = planner_service.submit_chat_turn(session_id, turn_request, actor=actor)
    except KeyError:
        return _error_response("未找到对应的会话。", code="chat_session_not_found", status_code=drf_status.HTTP_404_NOT_FOUND)
    except RuntimeError as exc:
        return _error_response(str(exc), code="chat_turn_conflict", status_code=drf_status.HTTP_409_CONFLICT)

    payload = {
        "session_id": session_id,
        "turn_id": turn.turn_id,
        "status": turn.status,
        "phase": _turn_phase(turn),
        "status_url": f"/api/chat/sessions/{session_id}/turns/{turn.turn_id}/",
        "stream_url": f"/api/chat/sessions/{session_id}/messages/stream/",
        "stream_supported": True,
    }
    if actor.guest_token and not actor.user:
        payload["guest_token"] = actor.guest_token
    return Response(payload, status=drf_status.HTTP_202_ACCEPTED)


@api_view(["POST"])
@renderer_classes([ServerSentEventRenderer, JSONRenderer])
def create_chat_turn_stream_view(request, session_id: str):
    payload, error_response = _parse_json_payload(request)
    if error_response is not None:
        return error_response
    try:
        turn_request = ChatTurnCreateRequest.model_validate(payload)
    except ValidationError as exc:
        return _validation_error(exc, "聊天回合参数无效。")

    actor = get_actor_context(request)
    guest_token = actor.guest_token
    try:
        turn = planner_service.submit_chat_turn(session_id, turn_request, actor=actor)
    except KeyError:
        return _error_response("未找到对应的会话。", code="chat_session_not_found", status_code=drf_status.HTTP_404_NOT_FOUND)
    except RuntimeError as exc:
        return _error_response(str(exc), code="chat_turn_conflict", status_code=drf_status.HTTP_409_CONFLICT)

    response = StreamingHttpResponse(
        _stream_chat_turn_events(
            session_id=session_id,
            turn=turn,
            actor=actor,
            guest_token=guest_token,
        ),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@api_view(["GET"])
def chat_turn_view(request, session_id: str, turn_id: str):
    turn = planner_service.get_chat_turn(
        session_id, turn_id, actor=get_actor_context(request)
    )
    if turn is None:
        return Response(
            {"error": "未找到对应的会话回合。", "code": "chat_turn_not_found", "source": "api"},
            status=drf_status.HTTP_404_NOT_FOUND,
        )
    return Response(_serialize_turn(turn))


@api_view(["POST"])
def save_trip_plan_view(request, session_id: str):
    payload, error_response = _parse_json_payload(request)
    if error_response is not None:
        return error_response
    try:
        save_request = SaveTripPlanRequest.model_validate(payload)
    except ValidationError as exc:
        return _validation_error(exc, "保存方案参数无效。")
    try:
        plan = planner_service.save_trip_plan(
            session_id,
            actor=get_actor_context(request),
            status=save_request.status,
            title=save_request.title,
        )
    except PermissionError:
        return Response(
            {"error": "保存方案前请先登录。", "code": "auth_required", "source": "api"},
            status=drf_status.HTTP_401_UNAUTHORIZED,
        )
    except KeyError:
        return Response(
            {"error": "未找到对应的会话。", "code": "chat_session_not_found", "source": "api"},
            status=drf_status.HTTP_404_NOT_FOUND,
        )
    except ValueError as exc:
        return _error_response(str(exc), code="plan_save_invalid", status_code=drf_status.HTTP_400_BAD_REQUEST)
    return Response(plan, status=drf_status.HTTP_201_CREATED)


@api_view(["GET"])
def trip_plans_view(request):
    try:
        items = planner_service.list_trip_plans(actor=get_actor_context(request))
        summary = planner_service.get_trip_plan_summary(actor=get_actor_context(request))
    except PermissionError:
        return Response(
            {"error": "请先登录后查看历史方案。", "code": "auth_required", "source": "api"},
            status=drf_status.HTTP_401_UNAUTHORIZED,
        )
    return Response(
        {
            "items": items,
            "count": summary["count"],
            "status_counts": summary["status_counts"],
        }
    )


@api_view(["GET", "DELETE"])
def trip_plan_view(request, plan_id: str):
    actor = get_actor_context(request)
    try:
        if request.method == "GET":
            plan = planner_service.get_trip_plan(plan_id, actor=actor)
            if plan is None:
                return Response(
                    {"error": "未找到对应的方案。", "code": "trip_plan_not_found", "source": "api"},
                    status=drf_status.HTTP_404_NOT_FOUND,
                )
            return Response(plan)
        deleted = planner_service.delete_trip_plan(plan_id, actor=actor)
    except PermissionError:
        return Response(
            {"error": "请先登录后访问方案。", "code": "auth_required", "source": "api"},
            status=drf_status.HTTP_401_UNAUTHORIZED,
        )
    if not deleted:
        return Response(
            {"error": "未找到对应的方案。", "code": "trip_plan_not_found", "source": "api"},
            status=drf_status.HTTP_404_NOT_FOUND,
        )
    return Response(status=drf_status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
def resume_trip_plan_view(request, plan_id: str):
    actor = get_actor_context(request)
    try:
        session = planner_service.resume_trip_plan(plan_id, actor=actor)
    except PermissionError:
        return Response(
            {"error": "请先登录后继续修订方案。", "code": "auth_required", "source": "api"},
            status=drf_status.HTTP_401_UNAUTHORIZED,
        )
    except KeyError:
        return Response(
            {"error": "未找到对应的方案。", "code": "trip_plan_not_found", "source": "api"},
            status=drf_status.HTTP_404_NOT_FOUND,
        )
    return Response(
        {
            "session_id": session.session_id,
            "title": session.title,
            "status": session.status,
            "session_url": f"/api/chat/sessions/{session.session_id}/",
        },
        status=drf_status.HTTP_201_CREATED,
    )
