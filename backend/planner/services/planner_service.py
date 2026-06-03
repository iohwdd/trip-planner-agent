from __future__ import annotations

from time import perf_counter
from collections import Counter

from django.conf import settings
from django.contrib.auth import get_user_model

from planner.domain.schemas import (
    ChatSession,
    ChatTurn,
    ChatTurnCreateRequest,
    PlannerRun,
    TripPlanningRequest,
)
from planner.graph.nodes import PlanningNodes
from planner.graph.workflow import TripPlannerWorkflow
from planner.integrations.qwen import QwenPlannerClient
from planner.models import PlanningJob
from planner.services.assistant_store import AssistantConversationStore
from planner.services.chat_session_store import ChatSessionStore
from planner.services.event_store import event_store
from planner.services.job_store import PlanningJobStore
from planner.services.live_data import LiveDataService
from planner.services.plan_store import TripPlanStore
from planner.services.persistence import plan_run_job_to_domain
from planner.services.planning_context import (
    build_assistant_message,
    build_assistant_reply_text,
    build_chat_context,
    build_form_context,
)
from planner.services.request_identity import ActorContext
from planner.services.route_directions import RouteDirectionsService
from planner.services.runtime_config import load_runtime_config

User = get_user_model()


class TripPlannerService:
    def __init__(self) -> None:
        self.config = load_runtime_config()
        self.chat_session_store = ChatSessionStore()
        self.assistant_store = AssistantConversationStore()
        self.plan_store = TripPlanStore()
        self.job_store = PlanningJobStore(
            timeout_seconds=settings.TRIP_PLANNER_JOB_TIMEOUT_SECONDS
        )
        self.live_data_service = LiveDataService(self.config)
        self.model_client = QwenPlannerClient(self.config.qwen)
        self.route_directions_service = RouteDirectionsService(self.config)
        self.workflow = TripPlannerWorkflow(
            PlanningNodes(
                self.live_data_service,
                self.model_client,
                self.route_directions_service,
            )
        )

    def start_run(
        self,
        request: TripPlanningRequest,
        *,
        actor: ActorContext,
    ) -> PlannerRun:
        run = self.create_run(request, actor=actor)
        self._maybe_execute_job(run.run_id)
        return self.get_run(run.run_id, actor=actor) or run

    def create_run(
        self,
        request: TripPlanningRequest,
        *,
        actor: ActorContext,
    ) -> PlannerRun:
        job = self.job_store.create_for_run(
            request,
            user=actor.user,
            guest_token=actor.guest_token,
        )
        self._track_event(
            "plan_run_created",
            owner=actor.user,
            guest_token=actor.guest_token,
            payload={"run_id": job.job_id},
        )
        return self.get_run(job.job_id, actor=actor) or plan_run_job_to_domain(job)

    def get_run(self, run_id: str, *, actor: ActorContext) -> PlannerRun | None:
        job = self.job_store.get_run(
            run_id,
            user=actor.user,
            guest_token=actor.guest_token,
        )
        return plan_run_job_to_domain(job) if job is not None else None

    def create_chat_session(self, *, actor: ActorContext) -> ChatSession:
        session = self.chat_session_store.create(
            user=actor.user,
            guest_token=actor.guest_token,
        )
        self._track_event(
            "chat_session_created",
            owner=actor.user,
            guest_token=actor.guest_token,
            session_id=session.session_id,
        )
        return session

    def list_chat_sessions(self, *, actor: ActorContext) -> list[dict]:
        return self.chat_session_store.list(
            user=actor.user,
            guest_token=actor.guest_token,
        )

    def get_recent_chat_session(self, *, actor: ActorContext) -> ChatSession | None:
        return self.chat_session_store.get_recent(
            user=actor.user,
            guest_token=actor.guest_token,
        )

    def get_chat_session(self, session_id: str, *, actor: ActorContext) -> ChatSession | None:
        return self.chat_session_store.get(
            session_id,
            user=actor.user,
            guest_token=actor.guest_token,
        )

    def rename_chat_session(
        self, session_id: str, title: str, *, actor: ActorContext
    ) -> ChatSession:
        return self.chat_session_store.rename_session(
            session_id,
            title,
            user=actor.user,
            guest_token=actor.guest_token,
        )

    def delete_chat_session(self, session_id: str, *, actor: ActorContext) -> bool:
        deleted = self.chat_session_store.delete_session(
            session_id,
            user=actor.user,
            guest_token=actor.guest_token,
        )
        if deleted:
            self._track_event(
                "chat_session_deleted",
                owner=actor.user,
                guest_token=actor.guest_token,
                session_id=session_id,
            )
        return deleted

    def submit_chat_turn(
        self,
        session_id: str,
        payload: ChatTurnCreateRequest,
        *,
        actor: ActorContext,
    ) -> ChatTurn:
        turn = self.chat_session_store.create_turn(
            session_id,
            payload,
            user=actor.user,
            guest_token=actor.guest_token,
        )
        job = self.job_store.create_for_turn(
            turn.turn_id,
            user=actor.user,
            guest_token=actor.guest_token,
        )
        self._track_event(
            "chat_turn_created",
            owner=actor.user,
            guest_token=actor.guest_token,
            session_id=session_id,
            turn_id=turn.turn_id,
            payload={"input_mode": turn.input_mode},
        )
        self._maybe_execute_job(job.job_id)
        return (
            self.get_chat_turn(session_id, turn.turn_id, actor=actor)
            or self.chat_session_store.get_turn(
                session_id, turn.turn_id, enforce_actor=False
            )
            or turn
        )

    def get_chat_turn(
        self, session_id: str, turn_id: str, *, actor: ActorContext
    ) -> ChatTurn | None:
        return self.chat_session_store.get_turn(
            session_id,
            turn_id,
            user=actor.user,
            guest_token=actor.guest_token,
        )

    def get_identity_summary(self, *, actor: ActorContext) -> dict:
        session_summary = self.chat_session_store.summary(
            user=actor.user,
            guest_token=actor.guest_token,
        )
        assistant_summary = self.assistant_store.summary(
            user=actor.user,
            guest_token=actor.guest_token,
        )
        plan_summary = (
            self.plan_store.summary(user=actor.user)
            if actor.user
            else {"count": 0, "status_counts": {}}
        )
        return {
            "guest": {
                "active": bool(actor.guest_token and not actor.user),
                "token_present": bool(actor.guest_token),
            },
            "asset_summary": {
                "session_count": session_summary["count"],
                "session_status_counts": session_summary["status_counts"],
                "recent_session_id": session_summary["recent_session_id"],
                "assistant_conversation_count": assistant_summary["count"],
                "recent_assistant_conversation_id": assistant_summary["recent_conversation_id"],
                "plan_count": plan_summary["count"],
                "plan_status_counts": plan_summary["status_counts"],
            },
            "capabilities": {
                "can_manage_sessions": True,
                "can_save_plan": bool(actor.user),
                "can_manage_plans": bool(actor.user),
                "can_set_password": bool(actor.user),
                "can_manage_knowledge_base": bool(actor.user and actor.user.is_staff),
            },
        }

    def get_chat_session_summary(self, *, actor: ActorContext) -> dict:
        return self.chat_session_store.summary(
            user=actor.user,
            guest_token=actor.guest_token,
        )

    def get_trip_plan_summary(self, *, actor: ActorContext) -> dict:
        if not actor.user:
            raise PermissionError("Authentication required.")
        return self.plan_store.summary(user=actor.user)

    def list_trip_plans(self, *, actor: ActorContext) -> list[dict]:
        if not actor.user:
            raise PermissionError("Authentication required.")
        return self.plan_store.list(user=actor.user)

    def save_trip_plan(
        self,
        session_id: str,
        *,
        actor: ActorContext,
        status: str,
        title: str | None = None,
    ) -> dict:
        if not actor.user:
            raise PermissionError("Authentication required.")
        plan = self.plan_store.save_from_session(
            session_id, user=actor.user, status=status, title=title
        )
        self._track_event(
            "trip_plan_saved",
            owner=actor.user,
            session_id=session_id,
            turn_id=plan.source_turn_id or "",
            plan_id=plan.plan_id,
            payload={"status": status, "version": plan.version},
        )
        return {
            "plan_id": plan.plan_id,
            "title": plan.title,
            "status": plan.status,
            "version": plan.version,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
        }

    def save_trip_plan_from_run(
        self,
        run_id: str,
        *,
        actor: ActorContext,
        status: str,
        title: str | None = None,
    ) -> dict:
        if not actor.user:
            raise PermissionError("Authentication required.")
        plan = self.plan_store.save_from_run(
            run_id, user=actor.user, status=status, title=title
        )
        self._track_event(
            "trip_plan_saved_from_run",
            owner=actor.user,
            plan_id=plan.plan_id,
            payload={"status": status, "run_id": run_id, "version": plan.version},
        )
        return {
            "plan_id": plan.plan_id,
            "title": plan.title,
            "status": plan.status,
            "version": plan.version,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
        }

    def get_trip_plan(self, plan_id: str, *, actor: ActorContext) -> dict | None:
        if not actor.user:
            raise PermissionError("Authentication required.")
        plan = self.plan_store.get(plan_id, user=actor.user)
        if plan is None:
            return None
        return {
            "plan_id": plan.plan_id,
            "title": plan.title,
            "status": plan.status,
            "version": plan.version,
            "source_session_id": plan.source_session_id,
            "source_turn_id": plan.source_turn_id,
            "source_job_id": plan.source_job_id,
            "source_type": "workbench_run" if plan.source_job_id else "chat_session",
            "constraints_snapshot": plan.constraints_snapshot,
            "result_snapshot": plan.result_snapshot,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
        }

    def delete_trip_plan(self, plan_id: str, *, actor: ActorContext) -> bool:
        if not actor.user:
            raise PermissionError("Authentication required.")
        deleted = self.plan_store.delete(plan_id, user=actor.user)
        if deleted:
            self._track_event("trip_plan_deleted", owner=actor.user, plan_id=plan_id)
        return deleted

    def resume_trip_plan(self, plan_id: str, *, actor: ActorContext) -> ChatSession:
        if not actor.user:
            raise PermissionError("Authentication required.")
        title, constraints, latest_result = self.plan_store.build_resume_seed(
            plan_id, user=actor.user
        )
        session = self.chat_session_store.create_from_plan(
            user=actor.user,
            title=f"{title}（继续修订）"[:120],
            confirmed_constraints=constraints,
            latest_result=latest_result,
        )
        self._track_event(
            "trip_plan_resumed",
            owner=actor.user,
            session_id=session.session_id,
            plan_id=plan_id,
        )
        return session

    def process_pending_jobs(self, *, limit: int = 1) -> int:
        for job in self.job_store.recover_stale_jobs():
            self._handle_timed_out_job(job)
        processed = 0
        while processed < limit:
            job = self.job_store.claim_next()
            if job is None:
                break
            self._run_claimed_job(job)
            processed += 1
        return processed

    def execute_job(self, job_id: str) -> bool:
        job = self.job_store.claim(job_id)
        if job is None:
            return False
        self._run_claimed_job(job)
        return True

    def _maybe_execute_job(self, job_id: str) -> None:
        if settings.TRIP_PLANNER_INLINE_JOBS:
            self.execute_job(job_id)

    def _run_claimed_job(self, job: PlanningJob) -> None:
        started = perf_counter()
        try:
            result = None
            captured_steps = []
            if job.job_type == PlanningJob.TYPE_PLAN_RUN:
                result, captured_steps = self._execute_run(job.job_id)
            elif job.job_type == PlanningJob.TYPE_CHAT_TURN and job.chat_turn_id:
                result, captured_steps = self._execute_chat_turn(job.chat_turn_id)
            else:
                raise RuntimeError("Unsupported planning job target.")
            duration_ms = int((perf_counter() - started) * 1000)
            metrics = self._build_job_metrics(
                captured_steps,
                result=result,
                duration_ms=duration_ms,
            )
            self.job_store.mark_completed(
                job.job_id,
                metrics=metrics,
            )
            self._track_event(
                "planning_job_completed",
                owner=job.owner,
                session_id=job.chat_turn.session_id if job.chat_turn is not None else "",
                turn_id=job.chat_turn_id or "",
                payload={"job_id": job.job_id, "job_type": job.job_type, **metrics},
            )
        except Exception as exc:
            if job.job_type == PlanningJob.TYPE_CHAT_TURN and job.chat_turn_id:
                turn = self.chat_session_store.get_turn(
                    job.chat_turn.session_id,  # type: ignore[union-attr]
                    job.chat_turn_id,
                    enforce_actor=False,
                )
                if turn is not None:
                    self.chat_session_store.fail_turn(
                        turn.session_id,
                        turn.turn_id,
                        str(exc),
                    )
            duration_ms = int((perf_counter() - started) * 1000)
            metrics = self._build_job_metrics(
                self._get_job_steps(job),
                duration_ms=duration_ms,
                error=str(exc),
            )
            self.job_store.mark_failed(
                job.job_id,
                str(exc),
                metrics=metrics,
            )
            self._track_event(
                "planning_job_failed",
                owner=job.owner,
                session_id=job.chat_turn.session_id if job.chat_turn is not None else "",
                turn_id=job.chat_turn_id or "",
                payload={"job_id": job.job_id, "job_type": job.job_type, **metrics},
            )

    def _execute_run(self, run_id: str):
        job = self.job_store.get_run(run_id, enforce_actor=False)
        run = plan_run_job_to_domain(job) if job is not None else None
        if run is None:
            raise KeyError(f"Run {run_id} not found.")
        context = build_form_context(run.request)
        captured_steps = []
        result = self.workflow.run_context(
            context,
            step_callback=lambda step: (
                captured_steps.append(step),
                self.job_store.add_step(run_id, step),
            )[-1],
        )
        result.execution_summary = captured_steps
        self.job_store.set_result(run_id, result)
        self._track_event(
            "plan_run_completed",
            owner=job.owner if job is not None else None,
            guest_token=job.guest_token if job is not None else None,
            payload={
                "run_id": run_id,
                "status": result.status,
                "assistant_mode": result.assistant_mode,
                "clarification_count": len(result.clarification_questions),
            },
        )
        return result, captured_steps

    def _execute_chat_turn(self, turn_id: str):
        from planner.models import ChatTurnRecord

        turn_record = (
            ChatTurnRecord.objects.select_related("session")
            .filter(turn_id=turn_id)
            .first()
        )
        if turn_record is None:
            raise KeyError(f"Chat turn {turn_id} not found.")
        session_id = turn_record.session_id
        self.chat_session_store.mark_turn_running(session_id, turn_id)
        session = self.chat_session_store.get(session_id, enforce_actor=False)
        if session is None:
            raise KeyError(f"Chat session {session_id} not found.")
        turn = self.chat_session_store.get_turn(session_id, turn_id, enforce_actor=False)
        if turn is None:
            raise KeyError(f"Chat turn {turn_id} not found.")
        payload = ChatTurnCreateRequest(
            message=turn.user_message.content if turn.request is None else None,
            request=turn.request,
        )
        captured_steps = []
        context = build_chat_context(session, payload)
        result = self.workflow.run_context(
            context,
            step_callback=lambda step: (
                captured_steps.append(step),
                self.chat_session_store.add_step(session_id, turn_id, step),
            )[-1],
        )
        result.execution_summary = captured_steps
        assistant_summary = result.trip_summary
        if result.clarification_questions:
            assistant_summary = " ".join(
                [assistant_summary]
                + [question.prompt for question in result.clarification_questions]
            ).strip()
        reply_text, message_type = build_assistant_reply_text(
            result.status, assistant_summary
        )
        assistant_message = build_assistant_message(
            reply_text,
            turn_id,
            message_type,
        )
        self.chat_session_store.complete_turn(
            session_id,
            turn_id,
            result=result,
            confirmed_constraints=context.confirmed_constraints,
            assistant_message=assistant_message,
        )
        self._track_event(
            "chat_turn_completed",
            owner=turn_record.session.owner,
            guest_token=turn_record.session.guest_token,
            session_id=session_id,
            turn_id=turn_id,
            payload={
                "status": result.status,
                "assistant_mode": result.assistant_mode,
                "clarification_count": len(result.clarification_questions),
            },
        )
        if result.clarification_questions:
            self._track_event(
                "chat_turn_clarification_requested",
                owner=turn_record.session.owner,
                guest_token=turn_record.session.guest_token,
                session_id=session_id,
                turn_id=turn_id,
                payload={
                    "clarification_count": len(result.clarification_questions),
                    "status": result.status,
                },
            )
        return result, captured_steps

    def _handle_timed_out_job(self, job: PlanningJob) -> None:
        message = job.error_message or "任务执行超时，已被系统回收。"
        metrics = self._build_timeout_metrics(job, message=message)
        self.job_store.update_metrics(job.job_id, metrics)
        if job.job_type == PlanningJob.TYPE_CHAT_TURN and job.chat_turn is not None:
            self.chat_session_store.fail_turn(
                job.chat_turn.session_id,
                job.chat_turn.turn_id,
                message,
            )
            self._track_event(
                "planning_job_timeout",
                owner=job.chat_turn.session.owner,
                guest_token=job.chat_turn.session.guest_token,
                session_id=job.chat_turn.session_id,
                turn_id=job.chat_turn.turn_id,
                payload={"job_id": job.job_id, "job_type": job.job_type, **metrics},
            )
            return
        if job.job_type == PlanningJob.TYPE_PLAN_RUN:
            self._track_event(
                "planning_job_timeout",
                owner=job.owner,
                guest_token=job.guest_token or None,
                payload={
                    "job_id": job.job_id,
                    "job_type": job.job_type,
                    **metrics,
                },
            )

    def _get_job_steps(self, job: PlanningJob):
        if job.job_type == PlanningJob.TYPE_CHAT_TURN and job.chat_turn is not None:
            turn = self.chat_session_store.get_turn(
                job.chat_turn.session_id,
                job.chat_turn.turn_id,
                enforce_actor=False,
            )
            return turn.steps if turn is not None else []
        if job.job_type == PlanningJob.TYPE_PLAN_RUN:
            run = self.job_store.get_run(job.job_id, enforce_actor=False)
            return plan_run_job_to_domain(run).steps if run is not None else []
        return []

    @staticmethod
    def _build_job_metrics(steps, *, result=None, duration_ms: int = 0, error: str | None = None):
        step_statuses = Counter()
        provider_statuses: dict[str, dict[str, int]] = {}
        step_duration_by_key_ms: dict[str, int] = {}
        serialized_steps = []
        for step in steps:
            step_statuses[step.status] += 1
            step_duration_ms = None
            if step.started_at and step.finished_at:
                step_duration_ms = max(
                    0,
                    int((step.finished_at - step.started_at).total_seconds() * 1000),
                )
                step_duration_by_key_ms[step.key] = (
                    step_duration_by_key_ms.get(step.key, 0) + step_duration_ms
                )
            serialized_steps.append(
                {
                    "key": step.key,
                    "status": step.status,
                    "duration_ms": step_duration_ms,
                }
            )
            for provider in step.provider_statuses:
                counters = provider_statuses.setdefault(provider.provider, {})
                counters[provider.status] = counters.get(provider.status, 0) + 1

        metrics = {
            "duration_ms": duration_ms,
            "step_count": len(steps),
            "step_status_counts": dict(step_statuses),
            "steps": serialized_steps,
            "step_duration_by_key_ms": step_duration_by_key_ms,
            "live_data_duration_ms": step_duration_by_key_ms.get("fetch_live_data", 0),
            "model_duration_ms": step_duration_by_key_ms.get("plan_trip", 0),
            "route_planning_duration_ms": step_duration_by_key_ms.get(
                "build_route_plan", 0
            ),
            "provider_status_counts": provider_statuses,
        }
        if result is not None:
            metrics.update(
                {
                    "result_status": result.status,
                    "assistant_mode": result.assistant_mode,
                    "clarification_count": len(result.clarification_questions),
                }
            )
        if error:
            metrics["error"] = error
        return metrics

    def _build_timeout_metrics(self, job: PlanningJob, *, message: str) -> dict:
        duration_ms = 0
        if job.started_at and job.finished_at:
            duration_ms = max(
                0,
                int((job.finished_at - job.started_at).total_seconds() * 1000),
            )
        return self._build_job_metrics(
            self._get_job_steps(job),
            duration_ms=duration_ms,
            error=message,
        )

    @staticmethod
    def _track_event(
        event_type: str,
        *,
        owner: User | None = None,
        guest_token: str | None = None,
        session_id: str = "",
        turn_id: str = "",
        plan_id: str = "",
        payload: dict | None = None,
    ) -> None:
        event_store.record(
            event_type,
            owner_id=str(owner.pk) if owner is not None else None,
            guest_token=guest_token or "",
            session_id=session_id,
            turn_id=turn_id,
            plan_id=plan_id,
            payload=payload or {},
        )


planner_service = TripPlannerService()
