from __future__ import annotations

from typing import Any, Iterable

from planner.domain.schemas import (
    ChatMessage,
    ChatSession,
    ChatTurn,
    ConfirmedConstraints,
    ExecutionStep,
    PlannerRun,
    TripPlanOutput,
    TripPlanningRequest,
)
from planner.models import ChatSessionRecord, ChatTurnRecord, PlanningJob


def model_to_json(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [model_to_json(item) for item in value]
    if isinstance(value, dict):
        return {key: model_to_json(item) for key, item in value.items()}
    return value


def _chat_message(data: dict[str, Any] | None) -> ChatMessage | None:
    if not data:
        return None
    return ChatMessage.model_validate(data)


def _confirmed_constraints(data: dict[str, Any] | None) -> ConfirmedConstraints:
    return ConfirmedConstraints.model_validate(data or {})


def _trip_request(data: dict[str, Any] | None) -> TripPlanningRequest | None:
    if not data:
        return None
    return TripPlanningRequest.model_validate(data)


def _trip_output(data: dict[str, Any] | None) -> TripPlanOutput | None:
    if not data:
        return None
    return TripPlanOutput.model_validate(data)


def _steps(data: Iterable[dict[str, Any]] | None) -> list[ExecutionStep]:
    return [ExecutionStep.model_validate(item) for item in (data or [])]


def _session_messages(turns: Iterable[ChatTurn]) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for turn in turns:
        messages.append(turn.user_message)
        if turn.assistant_message is not None:
            messages.append(turn.assistant_message)
    return messages


def turn_record_to_domain(record: ChatTurnRecord) -> ChatTurn:
    status = record.status if record.status != "timeout" else "failed"
    return ChatTurn(
        turn_id=record.turn_id,
        session_id=record.session_id,
        status=status,  # type: ignore[arg-type]
        input_mode=record.input_mode,  # type: ignore[arg-type]
        user_message=ChatMessage.model_validate(record.user_message),
        request=_trip_request(record.request_payload),
        confirmed_constraints=_confirmed_constraints(record.confirmed_constraints),
        steps=_steps(record.steps),
        result=_trip_output(record.result_payload),
        assistant_message=_chat_message(record.assistant_message),
        error=record.error or None,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def session_record_to_domain(
    record: ChatSessionRecord, turn_records: Iterable[ChatTurnRecord] | None = None
) -> ChatSession:
    turns = [
        turn_record_to_domain(turn)
        for turn in (
            turn_records
            if turn_records is not None
            else record.turn_records.order_by("created_at").all()
        )
    ]
    return ChatSession(
        session_id=record.session_id,
        title=record.title,
        status=record.status,  # type: ignore[arg-type]
        messages=_session_messages(turns),
        turns=turns,
        confirmed_constraints=_confirmed_constraints(record.confirmed_constraints),
        latest_result=_trip_output(record.latest_result),
        active_turn_id=record.active_turn_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def plan_run_job_to_domain(record: PlanningJob) -> PlannerRun:
    return PlannerRun(
        run_id=record.job_id,
        status=record.status,  # type: ignore[arg-type]
        request=TripPlanningRequest.model_validate(record.request_payload),
        steps=_steps(record.steps),
        result=_trip_output(record.result_payload),
        error=record.error_message or None,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def session_summary_dict(record: ChatSessionRecord) -> dict[str, Any]:
    latest_result = record.latest_result or {}
    return {
        "session_id": record.session_id,
        "title": record.title,
        "status": record.status,
        "latest_summary": record.latest_summary,
        "latest_result_status": latest_result.get("status"),
        "latest_plan_state": latest_result.get("plan_state"),
        "latest_generated_at": latest_result.get("generated_at"),
        "confirmed_constraints": record.confirmed_constraints,
        "last_accessed_at": record.last_accessed_at,
        "updated_at": record.updated_at,
        "created_at": record.created_at,
    }
