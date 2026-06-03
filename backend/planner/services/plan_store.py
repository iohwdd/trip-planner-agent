from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models import Max

from planner.domain.schemas import ConfirmedConstraints, TripPlanOutput
from planner.models import ChatSessionRecord, PlanningJob, TripPlanRecord
from planner.services.persistence import model_to_json

User = get_user_model()


class TripPlanStore:
    def summary(self, *, user: User) -> dict:
        query = TripPlanRecord.objects.filter(owner=user)
        status_counts = {
            row["status"]: row["count"]
            for row in query.values("status").annotate(count=Count("plan_id"))
        }
        return {
            "count": query.count(),
            "status_counts": status_counts,
        }

    def list(self, *, user: User) -> list[dict]:
        return [
            {
                "plan_id": record.plan_id,
                "title": record.title,
                "status": record.status,
                "version": record.version,
                "source_session_id": record.source_session_id,
                "source_turn_id": record.source_turn_id,
                "source_job_id": record.source_job_id,
                "source_type": "workbench_run" if record.source_job_id else "chat_session",
                "updated_at": record.updated_at,
                "created_at": record.created_at,
                "constraints_snapshot": record.constraints_snapshot,
                "result_summary": (record.result_snapshot or {}).get("trip_summary"),
                "result_status": (record.result_snapshot or {}).get("status"),
                "result_generated_at": (record.result_snapshot or {}).get("generated_at"),
            }
            for record in TripPlanRecord.objects.filter(owner=user).order_by("-updated_at")
        ]

    def save_from_session(
        self,
        session_id: str,
        *,
        user: User,
        status: str,
        title: str | None = None,
    ) -> TripPlanRecord:
        session = ChatSessionRecord.objects.filter(session_id=session_id, owner=user).first()
        if session is None:
            raise KeyError(f"Chat session {session_id} not found.")
        if not session.latest_result:
            raise ValueError("Current session has no plannable result to save.")
        latest_turn = session.turn_records.order_by("-created_at").first()
        version = (
            TripPlanRecord.objects.filter(owner=user, source_session=session)
            .aggregate(max_version=Max("version"))
            .get("max_version")
            or 0
        ) + 1
        return TripPlanRecord.objects.create(
            owner=user,
            source_session=session,
            source_turn=latest_turn,
            title=(title or session.title or "未命名方案")[:160],
            status=status,
            version=version,
            constraints_snapshot=session.confirmed_constraints,
            result_snapshot=session.latest_result,
        )

    def save_from_run(
        self,
        run_id: str,
        *,
        user: User,
        status: str,
        title: str | None = None,
    ) -> TripPlanRecord:
        job = PlanningJob.objects.filter(job_id=run_id, owner=user).first()
        if job is None:
            raise KeyError(f"Planning run {run_id} not found.")
        if not job.result_payload:
            raise ValueError("Current planning run has no plannable result to save.")
        version = (
            TripPlanRecord.objects.filter(owner=user, source_job=job)
            .aggregate(max_version=Max("version"))
            .get("max_version")
            or 0
        ) + 1
        request_payload = job.request_payload or {}
        destination = request_payload.get("destination") or "未命名目的地"
        days = request_payload.get("days")
        default_title = f"{destination} {days}天方案" if days else f"{destination} 方案"
        return TripPlanRecord.objects.create(
            owner=user,
            source_job=job,
            title=(title or default_title)[:160],
            status=status,
            version=version,
            constraints_snapshot=request_payload,
            result_snapshot=job.result_payload,
        )

    def get(self, plan_id: str, *, user: User) -> TripPlanRecord | None:
        return TripPlanRecord.objects.filter(plan_id=plan_id, owner=user).first()

    def delete(self, plan_id: str, *, user: User) -> bool:
        deleted, _ = TripPlanRecord.objects.filter(plan_id=plan_id, owner=user).delete()
        return deleted > 0

    def build_resume_seed(
        self,
        plan_id: str,
        *,
        user: User,
    ) -> tuple[str, ConfirmedConstraints, TripPlanOutput | None]:
        plan = self.get(plan_id, user=user)
        if plan is None:
            raise KeyError(f"Trip plan {plan_id} not found.")
        constraints = ConfirmedConstraints.model_validate(plan.constraints_snapshot or {})
        latest_result = (
            TripPlanOutput.model_validate(plan.result_snapshot)
            if plan.result_snapshot
            else None
        )
        return plan.title, constraints, latest_result
