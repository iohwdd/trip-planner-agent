import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trip_planner_backend.settings")

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from planner.api.views import (
    recent_chat_session_view,
    save_trip_plan_view,
    trip_plan_view,
    verify_auth_code_view,
)
from planner.domain.schemas import (
    ChatTurnCreateRequest,
    ConfirmedConstraints,
    ExecutionStep,
    ProviderStatus,
    TripPlanningRequest,
    TripPlanOutput,
)
from planner.models import (
    ChatSessionRecord,
    ChatTurnRecord,
    PlanningJob,
)
from planner.services.auth_service import AuthValidationError, auth_service
from planner.services.auth_state_store import AuthStateStore
from planner.services.chat_session_store import ChatSessionStore
from planner.services.event_store import event_store
from planner.services.job_store import PlanningJobStore
from planner.services.planner_service import planner_service
from planner.services.request_identity import ActorContext, create_guest_token

User = get_user_model()


def build_result(summary: str = "已生成上海两日游草案。") -> TripPlanOutput:
    return TripPlanOutput(
        status="success",
        plan_state="draft",
        trip_summary=summary,
        confirmed_constraints=ConfirmedConstraints(destination="上海", days=2),
    )


@override_settings(TRIP_PLANNER_INLINE_JOBS=False)
class AssetFlowTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()
        self.factory = APIRequestFactory()
        self.chat_session_store = ChatSessionStore()
        self.job_store = PlanningJobStore(timeout_seconds=1)
        self.auth_state_store = AuthStateStore()

    def test_recent_chat_session_returns_latest_record_for_guest(self) -> None:
        guest_token = create_guest_token()
        older = self.chat_session_store.create(
            guest_token=guest_token,
            title="旧会话",
            latest_result=build_result("旧草案"),
        )
        newer = self.chat_session_store.create(
            guest_token=guest_token,
            title="新会话",
            latest_result=build_result("新草案"),
        )
        ChatSessionRecord.objects.filter(session_id=older.session_id).update(
            last_accessed_at=timezone.now() - timedelta(hours=2)
        )
        ChatSessionRecord.objects.filter(session_id=newer.session_id).update(
            last_accessed_at=timezone.now()
        )

        request = self.factory.get(
            "/api/chat/sessions/recent/",
            HTTP_X_GUEST_TOKEN=guest_token,
        )
        response = recent_chat_session_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["session_id"], newer.session_id)
        self.assertEqual(response.data["latest_result"]["trip_summary"], "新草案")

    def test_verify_auth_code_migrates_guest_session_to_user(self) -> None:
        guest_token = create_guest_token()
        session = self.chat_session_store.create(
            guest_token=guest_token,
            title="游客上海计划",
            latest_result=build_result(),
        )
        self.auth_state_store.store_login_code(
            email="traveler@example.com",
            code="123456",
            request_ip="127.0.0.1",
            now=timezone.now(),
        )

        request = self.factory.post(
            "/api/auth/login/verify/",
            {
                "email": "traveler@example.com",
                "code": "123456",
                "guest_token": guest_token,
            },
            format="json",
        )
        response = verify_auth_code_view(request)

        self.assertEqual(response.status_code, 200)
        migrated = ChatSessionRecord.objects.get(session_id=session.session_id)
        user = User.objects.get(email="traveler@example.com")
        self.assertEqual(migrated.owner, user)
        self.assertIsNone(migrated.guest_token)
        migration_event = event_store.latest("guest_to_user_migration")
        self.assertIsNotNone(migration_event)
        self.assertEqual(migration_event["guest_token"], guest_token)
        self.assertEqual(migration_event["payload"]["chat_session_count"], 1)
        self.assertEqual(migration_event["payload"]["planning_job_count"], 0)

    def test_invalid_auth_code_increments_failed_attempts(self) -> None:
        self.auth_state_store.store_login_code(
            email="wrong-code@example.com",
            code="654321",
            request_ip="127.0.0.1",
            now=timezone.now(),
        )

        with self.assertRaises(AuthValidationError):
            auth_service.verify_login_code(
                email="wrong-code@example.com",
                code="000000",
            )

        auth_code = self.auth_state_store.get_login_code_state("wrong-code@example.com")
        self.assertIsNotNone(auth_code)
        self.assertEqual(auth_code.failed_attempts, 1)
        self.assertEqual(auth_code.status, AuthStateStore.CODE_STATUS_SENT)

    @override_settings(TRIP_PLANNER_AUTH_CODE_MAX_VERIFY_ATTEMPTS=1)
    def test_invalid_auth_code_expires_after_max_attempts(self) -> None:
        self.auth_state_store.store_login_code(
            email="locked@example.com",
            code="654321",
            request_ip="127.0.0.1",
            now=timezone.now(),
        )

        with self.assertRaises(AuthValidationError):
            auth_service.verify_login_code(email="locked@example.com", code="000000")

        auth_code = self.auth_state_store.get_login_code_state("locked@example.com")
        self.assertIsNotNone(auth_code)
        self.assertEqual(auth_code.failed_attempts, 1)
        self.assertEqual(auth_code.status, AuthStateStore.CODE_STATUS_EXPIRED)

    def test_password_login_migrates_guest_session_to_user(self) -> None:
        guest_token = create_guest_token()
        session = self.chat_session_store.create(
            guest_token=guest_token,
            title="游客密码登录计划",
            latest_result=build_result(),
        )
        user = User.objects.create_user(
            email="password@example.com",
            password="secret123",
        )

        payload = auth_service.login_with_password(
            email="password@example.com",
            password="secret123",
            guest_token=guest_token,
        )

        self.assertEqual(payload["user"]["id"], str(user.pk))
        migrated = ChatSessionRecord.objects.get(session_id=session.session_id)
        self.assertEqual(migrated.owner, user)
        self.assertIsNone(migrated.guest_token)

    def test_set_password_allows_password_login_after_code_login(self) -> None:
        user = User.objects.create_user(email="set-password@example.com")
        self.assertFalse(user.has_usable_password())

        result = auth_service.set_password(
            user=user,
            new_password="secret123",
        )
        self.assertEqual(result["message"], "密码已设置。")

        payload = auth_service.login_with_password(
            email="set-password@example.com",
            password="secret123",
        )
        self.assertTrue(payload["user"]["has_password"])

    def test_save_trip_plan_versions_increment_and_isolate_by_user(self) -> None:
        owner = User.objects.create_user(email="owner@example.com")
        other = User.objects.create_user(email="other@example.com")
        session = self.chat_session_store.create(
            user=owner,
            title="上海周末",
            confirmed_constraints=ConfirmedConstraints(destination="上海", days=2),
            latest_result=build_result(),
        )

        request = self.factory.post(
            f"/api/chat/sessions/{session.session_id}/plans/",
            {"status": "draft", "title": "上海周末 v1"},
            format="json",
        )
        force_authenticate(request, user=owner)
        first_response = save_trip_plan_view(request, session.session_id)

        request = self.factory.post(
            f"/api/chat/sessions/{session.session_id}/plans/",
            {"status": "final", "title": "上海周末 v2"},
            format="json",
        )
        force_authenticate(request, user=owner)
        second_response = save_trip_plan_view(request, session.session_id)

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)
        self.assertEqual(first_response.data["version"], 1)
        self.assertEqual(second_response.data["version"], 2)

        detail_request = self.factory.get(
            f"/api/trip-plans/{first_response.data['plan_id']}/"
        )
        force_authenticate(detail_request, user=other)
        denied_response = trip_plan_view(detail_request, first_response.data["plan_id"])
        self.assertEqual(denied_response.status_code, 404)

    def test_recover_stale_chat_job_marks_turn_and_session_failed(self) -> None:
        guest_token = create_guest_token()
        session = self.chat_session_store.create(
            guest_token=guest_token,
            title="待超时会话",
        )
        turn = self.chat_session_store.create_turn(
            session.session_id,
            ChatTurnCreateRequest(message="帮我规划上海两天"),
            guest_token=guest_token,
        )
        job = self.job_store.create_for_turn(turn.turn_id)
        PlanningJob.objects.filter(job_id=job.job_id).update(
            status=PlanningJob.STATUS_RUNNING,
            started_at=timezone.now() - timedelta(minutes=2),
            lease_expires_at=timezone.now() - timedelta(seconds=5),
        )

        processed = planner_service.process_pending_jobs(limit=0)

        self.assertEqual(processed, 0)
        job.refresh_from_db()
        turn_record = ChatTurnRecord.objects.get(turn_id=turn.turn_id)
        session_record = ChatSessionRecord.objects.get(session_id=session.session_id)
        self.assertEqual(job.status, PlanningJob.STATUS_TIMEOUT)
        self.assertEqual(turn_record.status, ChatTurnRecord.STATUS_FAILED)
        self.assertEqual(session_record.status, ChatSessionRecord.STATUS_FAILED)
        self.assertIn("超时", turn_record.error)
        self.assertEqual(job.metrics["error"], "任务执行超时，已被系统回收。")
        self.assertGreater(job.metrics["duration_ms"], 0)
        timeout_event = event_store.latest("planning_job_timeout")
        self.assertIsNotNone(timeout_event)
        self.assertEqual(timeout_event["payload"]["job_id"], job.job_id)
        self.assertEqual(timeout_event["payload"]["error"], "任务执行超时，已被系统回收。")

    def test_process_pending_chat_job_records_metrics(self) -> None:
        guest_token = create_guest_token()
        session = self.chat_session_store.create(
            guest_token=guest_token,
            title="指标测试会话",
        )
        turn = self.chat_session_store.create_turn(
            session.session_id,
            ChatTurnCreateRequest(message="帮我规划上海两天"),
            guest_token=guest_token,
        )
        job = self.job_store.create_for_turn(turn.turn_id)
        started_at = timezone.now() - timedelta(seconds=3)
        finished_at = timezone.now() - timedelta(seconds=1)

        def fake_run_context(_context, step_callback):
            step_callback(
                ExecutionStep(
                    key="fetch_live_data",
                    title="查询实时数据",
                    status="completed",
                    detail="已获取实时数据",
                    started_at=started_at,
                    finished_at=finished_at,
                    provider_statuses=[
                        ProviderStatus(
                            provider="amap",
                            status="success",
                            message="ok",
                        )
                    ],
                )
            )
            return build_result()

        original = planner_service.workflow.run_context
        planner_service.workflow.run_context = fake_run_context
        try:
            processed = planner_service.process_pending_jobs(limit=1)
        finally:
            planner_service.workflow.run_context = original

        self.assertEqual(processed, 1)
        job.refresh_from_db()
        self.assertEqual(job.status, PlanningJob.STATUS_COMPLETED)
        self.assertEqual(job.metrics["result_status"], "success")
        self.assertEqual(job.metrics["assistant_mode"], "travel")
        self.assertEqual(job.metrics["step_count"], 1)
        self.assertEqual(job.metrics["live_data_duration_ms"], 2000)
        self.assertEqual(
            job.metrics["step_duration_by_key_ms"]["fetch_live_data"],
            2000,
        )
        self.assertEqual(
            job.metrics["provider_status_counts"]["amap"]["success"],
            1,
        )
        self.assertIsNotNone(event_store.latest("planning_job_completed"))

    def test_process_pending_queued_run_after_restart_records_run_metrics(self) -> None:
        guest_token = create_guest_token()
        request = TripPlanningRequest(
            destination="上海",
            city="上海",
            days=2,
            budget=2800,
            interests=["地标"],
        )
        run = planner_service.start_run(
            request,
            actor=ActorContext(user=None, guest_token=guest_token),
        )
        started_at = timezone.now() - timedelta(seconds=4)
        finished_at = timezone.now() - timedelta(seconds=1)

        def fake_run_context(_context, step_callback):
            step_callback(
                ExecutionStep(
                    key="plan_trip",
                    title="生成路线草案",
                    status="completed",
                    detail="已生成草案",
                    started_at=started_at,
                    finished_at=finished_at,
                )
            )
            return build_result("上海两日游草案已生成。")

        original = planner_service.workflow.run_context
        planner_service.workflow.run_context = fake_run_context
        try:
            processed = planner_service.process_pending_jobs(limit=1)
        finally:
            planner_service.workflow.run_context = original

        self.assertEqual(processed, 1)
        job = PlanningJob.objects.get(job_id=run.run_id)
        self.assertEqual(job.status, PlanningJob.STATUS_COMPLETED)
        self.assertEqual(job.metrics["model_duration_ms"], 3000)
        self.assertEqual(
            job.metrics["step_duration_by_key_ms"]["plan_trip"],
            3000,
        )
        completed_event = event_store.latest("plan_run_completed")
        self.assertIsNotNone(completed_event)
        self.assertEqual(completed_event["payload"]["run_id"], run.run_id)
        refreshed_run = planner_service.get_run(
            run.run_id,
            actor=ActorContext(user=None, guest_token=guest_token),
        )
        self.assertIsNotNone(refreshed_run)
        self.assertEqual(refreshed_run.status, "completed")
        self.assertEqual(
            refreshed_run.result.trip_summary,
            "上海两日游草案已生成。",
        )

    def test_process_pending_chat_job_marks_failure(self) -> None:
        guest_token = create_guest_token()
        session = self.chat_session_store.create(
            guest_token=guest_token,
            title="失败测试会话",
        )
        turn = self.chat_session_store.create_turn(
            session.session_id,
            ChatTurnCreateRequest(message="帮我规划上海两天"),
            guest_token=guest_token,
        )
        job = self.job_store.create_for_turn(turn.turn_id)

        original = planner_service.workflow.run_context
        planner_service.workflow.run_context = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("模型调用失败")
        )
        try:
            processed = planner_service.process_pending_jobs(limit=1)
        finally:
            planner_service.workflow.run_context = original

        self.assertEqual(processed, 1)
        job.refresh_from_db()
        session_record = ChatSessionRecord.objects.get(session_id=session.session_id)
        turn_record = ChatTurnRecord.objects.get(turn_id=turn.turn_id)
        self.assertEqual(job.status, PlanningJob.STATUS_FAILED)
        self.assertEqual(turn_record.status, ChatTurnRecord.STATUS_FAILED)
        self.assertEqual(session_record.status, ChatSessionRecord.STATUS_FAILED)
        self.assertEqual(job.metrics["error"], "模型调用失败")
        self.assertIsNotNone(event_store.latest("planning_job_failed"))

    def test_guest_plan_login_save_and_resume_end_to_end(self) -> None:
        def fake_run_context(_context, step_callback):
            step_callback(
                ExecutionStep(
                    key="plan_trip",
                    title="生成模型回复",
                    status="completed",
                    detail="已生成草案",
                )
            )
            return build_result("上海两日游草案已生成。")

        original = planner_service.workflow.run_context
        planner_service.workflow.run_context = fake_run_context
        try:
            create_session_response = self.client.post("/api/chat/sessions/")
            self.assertEqual(create_session_response.status_code, 201)
            guest_token = create_session_response.data["guest_token"]
            session_id = create_session_response.data["session_id"]

            message_response = self.client.post(
                f"/api/chat/sessions/{session_id}/messages/",
                {"message": "帮我规划上海两日游"},
                format="json",
                HTTP_X_GUEST_TOKEN=guest_token,
            )
            self.assertEqual(message_response.status_code, 202)
            planner_service.process_pending_jobs(limit=1)

            session_response = self.client.get(
                f"/api/chat/sessions/{session_id}/",
                HTTP_X_GUEST_TOKEN=guest_token,
            )
            self.assertEqual(session_response.status_code, 200)
            self.assertEqual(
                session_response.data["latest_result"]["trip_summary"],
                "上海两日游草案已生成。",
            )

            self.auth_state_store.store_login_code(
                email="flow@example.com",
                code="123456",
                request_ip="127.0.0.1",
                now=timezone.now(),
            )
            login_response = self.client.post(
                "/api/auth/login/verify/",
                {
                    "email": "flow@example.com",
                    "code": "123456",
                    "guest_token": guest_token,
                },
                format="json",
            )
            self.assertEqual(login_response.status_code, 200)
            access_token = login_response.data["access_token"]

            plan_response = self.client.post(
                f"/api/chat/sessions/{session_id}/plans/",
                {"status": "draft", "title": "上海两日游 v1"},
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {access_token}",
            )
            self.assertEqual(plan_response.status_code, 201)
            plan_id = plan_response.data["plan_id"]

            list_response = self.client.get(
                "/api/trip-plans/",
                HTTP_AUTHORIZATION=f"Bearer {access_token}",
            )
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(len(list_response.data["items"]), 1)

            resume_response = self.client.post(
                f"/api/trip-plans/{plan_id}/resume/",
                HTTP_AUTHORIZATION=f"Bearer {access_token}",
            )
            self.assertEqual(resume_response.status_code, 201)

            resumed_session = self.chat_session_store.get(
                resume_response.data["session_id"],
                user=User.objects.get(email="flow@example.com"),
            )
            self.assertIsNotNone(resumed_session)
            self.assertEqual(
                resumed_session.latest_result.trip_summary,
                "上海两日游草案已生成。",
            )
        finally:
            planner_service.workflow.run_context = original

    def test_guest_plan_login_and_continue_historical_session_end_to_end(self) -> None:
        def fake_run_context(_context, step_callback):
            step_callback(
                ExecutionStep(
                    key="plan_trip",
                    title="生成模型回复",
                    status="completed",
                    detail="已生成草案",
                )
            )
            return build_result("上海两日游草案已生成。")

        original = planner_service.workflow.run_context
        planner_service.workflow.run_context = fake_run_context
        try:
            create_session_response = self.client.post("/api/chat/sessions/")
            self.assertEqual(create_session_response.status_code, 201)
            guest_token = create_session_response.data["guest_token"]
            session_id = create_session_response.data["session_id"]

            message_response = self.client.post(
                f"/api/chat/sessions/{session_id}/messages/",
                {"message": "帮我规划上海两日游"},
                format="json",
                HTTP_X_GUEST_TOKEN=guest_token,
            )
            self.assertEqual(message_response.status_code, 202)
            planner_service.process_pending_jobs(limit=1)

            self.auth_state_store.store_login_code(
                email="history-flow@example.com",
                code="123456",
                request_ip="127.0.0.1",
                now=timezone.now(),
            )
            login_response = self.client.post(
                "/api/auth/login/verify/",
                {
                    "email": "history-flow@example.com",
                    "code": "123456",
                    "guest_token": guest_token,
                },
                format="json",
            )
            self.assertEqual(login_response.status_code, 200)
            access_token = login_response.data["access_token"]

            sessions_response = self.client.get(
                "/api/chat/sessions/",
                HTTP_AUTHORIZATION=f"Bearer {access_token}",
            )
            self.assertEqual(sessions_response.status_code, 200)
            self.assertEqual(len(sessions_response.data["items"]), 1)
            self.assertEqual(
                sessions_response.data["items"][0]["session_id"],
                session_id,
            )

            plan_response = self.client.post(
                f"/api/chat/sessions/{session_id}/plans/",
                {"status": "draft", "title": "上海两日游草案"},
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {access_token}",
            )
            self.assertEqual(plan_response.status_code, 201)

            continue_response = self.client.post(
                f"/api/chat/sessions/{session_id}/messages/",
                {"message": "保留外滩，整体节奏放松一点"},
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {access_token}",
            )
            self.assertEqual(continue_response.status_code, 202)
            planner_service.process_pending_jobs(limit=1)

            session_detail_response = self.client.get(
                f"/api/chat/sessions/{session_id}/",
                HTTP_AUTHORIZATION=f"Bearer {access_token}",
            )
            self.assertEqual(session_detail_response.status_code, 200)
            self.assertEqual(len(session_detail_response.data["turns"]), 2)
            self.assertEqual(
                session_detail_response.data["turns"][-1]["user_message"]["content"],
                "保留外滩，整体节奏放松一点",
            )
            self.assertEqual(
                session_detail_response.data["latest_result"]["trip_summary"],
                "上海两日游草案已生成。",
            )
        finally:
            planner_service.workflow.run_context = original
