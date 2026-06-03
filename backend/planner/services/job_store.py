from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from planner.domain.schemas import ExecutionStep, TripPlanOutput, TripPlanningRequest
from planner.models import PlanningJob
from planner.services.persistence import model_to_json
from planner.services.planning_queue import build_planning_queue
from planner.services.runtime_config import load_runtime_config

User = get_user_model()


class PlanningJobStore:
    def __init__(self, *, timeout_seconds: int) -> None:
        self.timeout_seconds = timeout_seconds
        self.queue = build_planning_queue(load_runtime_config().redis)

    def create_for_run(
        self,
        request: TripPlanningRequest,
        *,
        user: User | None = None,
        guest_token: str | None = None,
    ) -> PlanningJob:
        job = PlanningJob.objects.create(
            job_type=PlanningJob.TYPE_PLAN_RUN,
            owner=user,
            guest_token="" if user else (guest_token or ""),
            request_payload=model_to_json(request),
            timeout_seconds=self.timeout_seconds,
        )
        if self.queue.available:
            self.queue.enqueue(job.job_id)
        return job

    def create_for_turn(
        self,
        turn_id: str,
        *,
        user: User | None = None,
        guest_token: str | None = None,
    ) -> PlanningJob:
        from planner.models import ChatTurnRecord

        turn = ChatTurnRecord.objects.get(turn_id=turn_id)
        job = PlanningJob.objects.create(
            job_type=PlanningJob.TYPE_CHAT_TURN,
            chat_turn=turn,
            owner=user,
            guest_token="" if user else (guest_token or ""),
            timeout_seconds=self.timeout_seconds,
        )
        if self.queue.available:
            self.queue.enqueue(job.job_id)
        return job

    def get(self, job_id: str) -> PlanningJob | None:
        return PlanningJob.objects.filter(job_id=job_id).first()

    def claim(self, job_id: str) -> PlanningJob | None:
        with transaction.atomic():
            job = PlanningJob.objects.select_for_update().filter(job_id=job_id).first()
            if job is None or job.status != PlanningJob.STATUS_QUEUED:
                return None
            now = timezone.now()
            job.status = PlanningJob.STATUS_RUNNING
            job.attempts += 1
            job.started_at = job.started_at or now
            job.lease_expires_at = now + timedelta(seconds=job.timeout_seconds)
            job.updated_at = now
            job.save(
                update_fields=[
                    "status",
                    "attempts",
                    "started_at",
                    "lease_expires_at",
                    "updated_at",
                ]
            )
            return job

    def claim_next(self) -> PlanningJob | None:
        if self.queue.available:
            while True:
                job_id = self.queue.pop_next()
                if job_id is None:
                    break
                job = self.claim(job_id)
                if job is not None:
                    return job

        with transaction.atomic():
            job = (
                PlanningJob.objects.select_for_update()
                .filter(status=PlanningJob.STATUS_QUEUED)
                .order_by("created_at")
                .first()
            )
            if job is None:
                return None
            now = timezone.now()
            job.status = PlanningJob.STATUS_RUNNING
            job.attempts += 1
            job.started_at = job.started_at or now
            job.lease_expires_at = now + timedelta(seconds=job.timeout_seconds)
            job.updated_at = now
            job.save(
                update_fields=[
                    "status",
                    "attempts",
                    "started_at",
                    "lease_expires_at",
                    "updated_at",
                ]
            )
            return job

    def mark_completed(self, job_id: str, *, metrics: dict | None = None) -> None:
        PlanningJob.objects.filter(job_id=job_id).update(
            status=PlanningJob.STATUS_COMPLETED,
            lease_expires_at=None,
            finished_at=timezone.now(),
            metrics=metrics or {},
            updated_at=timezone.now(),
        )

    def add_step(self, job_id: str, step: ExecutionStep) -> None:
        job = PlanningJob.objects.get(job_id=job_id)
        job.steps = [*job.steps, model_to_json(step)]
        job.updated_at = timezone.now()
        job.save(update_fields=["steps", "updated_at"])

    def set_result(self, job_id: str, result: TripPlanOutput) -> None:
        PlanningJob.objects.filter(job_id=job_id).update(
            result_payload=model_to_json(result),
            updated_at=timezone.now(),
        )

    def get_run(
        self,
        job_id: str,
        *,
        user: User | None = None,
        guest_token: str | None = None,
        enforce_actor: bool = True,
    ) -> PlanningJob | None:
        query = PlanningJob.objects.filter(job_type=PlanningJob.TYPE_PLAN_RUN)
        if enforce_actor:
            if user and getattr(user, "is_authenticated", False):
                query = query.filter(owner=user)
            elif guest_token:
                query = query.filter(owner__isnull=True, guest_token=guest_token)
            else:
                query = query.none()
        return query.filter(job_id=job_id).first()

    def mark_failed(
        self, job_id: str, message: str, *, timeout: bool = False, metrics: dict | None = None
    ) -> None:
        PlanningJob.objects.filter(job_id=job_id).update(
            status=PlanningJob.STATUS_TIMEOUT if timeout else PlanningJob.STATUS_FAILED,
            error_message=message,
            lease_expires_at=None,
            finished_at=timezone.now(),
            metrics=metrics or {},
            updated_at=timezone.now(),
        )

    def update_metrics(self, job_id: str, metrics: dict) -> None:
        PlanningJob.objects.filter(job_id=job_id).update(
            metrics=metrics,
            updated_at=timezone.now(),
        )

    def recover_stale_jobs(self) -> list[PlanningJob]:
        now = timezone.now()
        with transaction.atomic():
            jobs = list(
                PlanningJob.objects.select_for_update()
                .select_related("chat_turn__session")
                .filter(
                    status=PlanningJob.STATUS_RUNNING,
                    lease_expires_at__lt=now,
                )
            )
            for job in jobs:
                job.status = PlanningJob.STATUS_TIMEOUT
                job.error_message = "任务执行超时，已被系统回收。"
                job.finished_at = now
                job.lease_expires_at = None
                job.updated_at = now
                job.save(
                    update_fields=[
                        "status",
                        "error_message",
                        "finished_at",
                        "lease_expires_at",
                        "updated_at",
                    ]
                )
            return jobs
