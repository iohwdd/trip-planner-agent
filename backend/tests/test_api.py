import json
import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trip_planner_backend.settings")

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import ProgrammingError
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from planner.api.views import (
    assistant_conversation_view,
    assistant_conversations_view,
    auth_me_view,
    chat_session_view,
    chat_sessions_view,
    chat_turn_view,
    create_assistant_message_stream_view,
    create_chat_turn_view,
    create_assistant_message_view,
    create_chat_turn_stream_view,
    health_check,
    knowledge_dashboard_view,
    knowledge_overview_view,
    knowledge_documents_view,
    knowledge_document_view,
    knowledge_document_retry_view,
    knowledge_reindex_view,
    password_login_view,
    plan_trip_stream_view,
    recent_assistant_conversation_view,
    plan_trip_view,
    save_run_plan_view,
    save_trip_plan_view,
    send_auth_code_view,
    set_password_view,
    trip_plans_view,
    verify_auth_code_view,
)
from planner.domain.schemas import ChatTurn, ChatMessage, TripPlanOutput
from planner.models import KnowledgeDocumentRecord, TripPlanRecord, User
from planner.services.knowledge_base_service import KnowledgeBaseService, _safe_filename
from rest_framework.test import force_authenticate


@override_settings(TRIP_PLANNER_INLINE_JOBS=False)
class ApiTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_health_check(self) -> None:
        response = health_check(self.factory.get("/api/health/"))
        self.assertEqual(response.status_code, 200)

    def test_plan_trip_rejects_invalid_json(self) -> None:
        request = self.factory.post(
            "/api/plans/",
            data="{invalid}",
            content_type="application/json",
        )
        response = plan_trip_view(request)
        self.assertEqual(response.status_code, 400)

    def test_plan_trip_accepts_valid_payload(self) -> None:
        request = self.factory.post(
            "/api/plans/",
            data=json.dumps(
                {
                    "destination": "Hangzhou",
                    "days": 2,
                    "budget": 2000,
                    "interests": ["tea", "lake"],
                }
            ),
            content_type="application/json",
        )
        response = plan_trip_view(request)
        self.assertEqual(response.status_code, 202)

    def test_create_assistant_conversation_returns_201(self) -> None:
        response = assistant_conversations_view(
            self.factory.post("/api/assistant/conversations/")
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("conversation_id", response.data)
        self.assertIn("guest_token", response.data)

    def test_create_assistant_message_returns_updated_conversation(self) -> None:
        created = assistant_conversations_view(
            self.factory.post("/api/assistant/conversations/")
        ).data
        request = self.factory.post(
            f"/api/assistant/conversations/{created['conversation_id']}/messages/",
            data=json.dumps({"message": "你好，帮我解释一下为什么上海适合 citywalk"}),
            content_type="application/json",
            HTTP_X_GUEST_TOKEN=created["guest_token"],
        )

        response = create_assistant_message_view(request, created["conversation_id"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["messages"]), 2)
        self.assertEqual(response.data["messages"][0]["role"], "user")
        self.assertEqual(response.data["messages"][1]["role"], "assistant")

    def test_create_assistant_message_passes_knowledge_context_to_model_client(self) -> None:
        created = assistant_conversations_view(
            self.factory.post("/api/assistant/conversations/")
        ).data
        request = self.factory.post(
            f"/api/assistant/conversations/{created['conversation_id']}/messages/",
            data=json.dumps({"message": "北京有哪些适合夜游的路线"}),
            content_type="application/json",
            HTTP_X_GUEST_TOKEN=created["guest_token"],
        )

        with mock.patch(
            "planner.services.assistant_service.knowledge_base_service.retrieve",
            return_value=[
                mock.Mock(
                    title="北京夜游",
                    heading_path="路线",
                    content="可以考虑亮马河夜游和什刹海步行。"
                )
            ],
        ), mock.patch(
            "planner.services.assistant_service.assistant_service.model_client.generate_assistant_reply",
            return_value="可以重点考虑亮马河和什刹海夜游。"
        ) as generate_mock:
            response = create_assistant_message_view(request, created["conversation_id"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(generate_mock.call_args.kwargs["knowledge_context"][0]["title"], "北京夜游")

    def test_create_assistant_message_falls_back_when_knowledge_retrieval_fails(self) -> None:
        created = assistant_conversations_view(
            self.factory.post("/api/assistant/conversations/")
        ).data
        request = self.factory.post(
            f"/api/assistant/conversations/{created['conversation_id']}/messages/",
            data=json.dumps({"message": "帮我总结一下杭州春天适合怎么玩"}),
            content_type="application/json",
            HTTP_X_GUEST_TOKEN=created["guest_token"],
        )

        with mock.patch(
            "planner.services.assistant_service.knowledge_base_service.retrieve",
            side_effect=RuntimeError("retrieve failed"),
        ), mock.patch(
            "planner.services.assistant_service.assistant_service.model_client.generate_assistant_reply",
            return_value="西湖、龙井和梅家坞都适合春季安排。"
        ) as generate_mock:
            response = create_assistant_message_view(request, created["conversation_id"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(generate_mock.call_args.kwargs["knowledge_context"], [])

    def test_create_assistant_message_stream_returns_sse_events(self) -> None:
        created = assistant_conversations_view(
            self.factory.post("/api/assistant/conversations/")
        ).data
        request = self.factory.post(
            f"/api/assistant/conversations/{created['conversation_id']}/messages/stream/",
            data=json.dumps({"message": "解释一下上海适合 citywalk 的原因"}),
            content_type="application/json",
            HTTP_X_GUEST_TOKEN=created["guest_token"],
            HTTP_ACCEPT="text/event-stream",
        )

        conversation = {
            "conversation_id": created["conversation_id"],
            "title": "上海 citywalk",
            "messages": [
                {
                    "message_id": "m1",
                    "role": "user",
                    "content": "解释一下上海适合 citywalk 的原因",
                    "message_type": "text",
                },
                {
                    "message_id": "m2",
                    "role": "assistant",
                    "content": "上海街区密度高，步行体验连续，街景层次也更丰富。",
                    "message_type": "text",
                },
            ],
        }

        with mock.patch(
            "planner.api.views.assistant_service.stream_reply_chunks",
            return_value=iter(["上海街区密度高，", "步行体验连续，", "街景层次也更丰富。"]),
        ), mock.patch(
            "planner.api.views.assistant_service.append_message_reply",
            return_value=conversation,
        ):
            response = create_assistant_message_stream_view(
                request, created["conversation_id"]
            )
            payload = b"".join(
                chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
                for chunk in response.streaming_content
            ).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertIn("event: message.accepted", payload)
        self.assertIn("event: message.delta", payload)
        self.assertIn("event: message.complete", payload)

    def test_plan_trip_stream_returns_sse_events(self) -> None:
        request = self.factory.post(
            "/api/plans/stream/",
            data=json.dumps(
                {
                    "destination": "上海",
                    "city": "上海",
                    "days": 2,
                    "budget": 3000,
                    "interests": ["citywalk"],
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="text/event-stream",
        )

        with mock.patch(
            "planner.api.views.planner_service.create_run",
            return_value=mock.Mock(run_id="run-stream"),
        ), mock.patch(
            "planner.api.views.planner_service.get_run",
            side_effect=[
                mock.Mock(
                    run_id="run-stream",
                    status="queued",
                    steps=[],
                    result=None,
                    error=None,
                ),
                mock.Mock(
                    run_id="run-stream",
                    status="running",
                    steps=[
                        mock.Mock(
                            key="normalize_input",
                            model_dump=lambda mode="json": {
                                "key": "normalize_input",
                                "title": "规范化用户输入",
                                "status": "completed",
                                "detail": "已整理当前回合输入、历史上下文和默认值。",
                            },
                        )
                    ],
                    result=None,
                    error=None,
                ),
                mock.Mock(
                    run_id="run-stream",
                    status="completed",
                    steps=[],
                    result=TripPlanOutput(
                        status="success",
                        plan_state="final",
                        trip_summary="上海两日游已生成。",
                    ),
                    error=None,
                ),
            ],
        ), mock.patch(
            "planner.api.views.threading.Thread"
        ) as thread_mock, mock.patch("planner.api.views.time.sleep", return_value=None):
            response = plan_trip_stream_view(request)
            payload = b"".join(
                chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
                for chunk in response.streaming_content
            ).decode("utf-8")

        thread_mock.return_value.start.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertIn("event: run.created", payload)
        self.assertIn("event: run.status", payload)
        self.assertIn("event: run.step", payload)
        self.assertIn("event: run.complete", payload)

    def test_recent_assistant_conversation_returns_latest_record(self) -> None:
        created = assistant_conversations_view(
            self.factory.post("/api/assistant/conversations/")
        ).data

        response = recent_assistant_conversation_view(
            self.factory.get(
                "/api/assistant/conversations/recent/",
                HTTP_X_GUEST_TOKEN=created["guest_token"],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["conversation_id"], created["conversation_id"])

    def test_auth_me_exposes_knowledge_management_capability_for_staff(self) -> None:
        user = User.objects.create_user(email="staff@example.com", is_staff=True)
        request = self.factory.get("/api/auth/me/")
        force_authenticate(request, user=user)

        response = auth_me_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["user"]["is_staff"])
        self.assertTrue(response.data["capabilities"]["can_manage_knowledge_base"])

    def test_knowledge_dashboard_requires_staff(self) -> None:
        user = User.objects.create_user(email="member@example.com")
        request = self.factory.get("/api/knowledge/")
        force_authenticate(request, user=user)

        response = knowledge_dashboard_view(request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "knowledge_forbidden")

    def test_knowledge_dashboard_returns_payload_for_staff(self) -> None:
        user = User.objects.create_user(email="staff2@example.com", is_staff=True)
        request = self.factory.get("/api/knowledge/")
        force_authenticate(request, user=user)

        with mock.patch(
            "planner.api.views.knowledge_base_service.get_dashboard_payload",
            return_value={
                "knowledge_base": {"knowledge_base_id": "kb-1", "name": "智能助手知识库"},
                "documents": [],
                "summary": {"document_count": 0, "ready_count": 0},
            },
        ):
            response = knowledge_dashboard_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["knowledge_base"]["knowledge_base_id"], "kb-1")

    def test_knowledge_dashboard_returns_schema_hint_when_migration_missing(self) -> None:
        user = User.objects.create_user(email="staff2b@example.com", is_staff=True)
        request = self.factory.get("/api/knowledge/")
        force_authenticate(request, user=user)

        with mock.patch(
            "planner.api.views.knowledge_base_service.get_dashboard_payload",
            side_effect=ProgrammingError(1054, "Unknown column 'status_detail' in 'field list'"),
        ):
            response = knowledge_dashboard_view(request)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "knowledge_schema_outdated")
        self.assertIn("manage.py migrate", response.data["details"]["hint"])

    def test_knowledge_overview_returns_payload_for_staff(self) -> None:
        user = User.objects.create_user(email="staff-overview@example.com", is_staff=True)
        request = self.factory.get("/api/knowledge/overview/")
        force_authenticate(request, user=user)

        with mock.patch(
            "planner.api.views.knowledge_base_service.get_overview_payload",
            return_value={
                "knowledge_base": {"knowledge_base_id": "kb-1", "name": "智能助手知识库"},
                "document_count": 3,
                "indexed_document_count": 2,
                "total_file_size_bytes": 4096,
                "total_file_size_label": "4.0 KB",
            },
        ):
            response = knowledge_overview_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["document_count"], 3)
        self.assertEqual(response.data["indexed_document_count"], 2)
        self.assertEqual(response.data["total_file_size_bytes"], 4096)

    def test_knowledge_document_upload_calls_service(self) -> None:
        user = User.objects.create_user(email="staff3@example.com", is_staff=True)
        upload = SimpleUploadedFile("guide.md", b"# title\ncontent", content_type="text/markdown")
        request = self.factory.post("/api/knowledge/documents/", data={"file": upload})
        force_authenticate(request, user=user)

        with mock.patch(
            "planner.api.views.knowledge_base_service.upload_document",
            return_value={
                "document_id": "doc-1",
                "title": "guide",
                "status": "pending",
                "status_detail": "文件已上传，等待解析",
                "progress_percent": 5,
            },
        ) as upload_mock:
            response = knowledge_documents_view(request)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["document_id"], "doc-1")
        self.assertEqual(upload_mock.call_args.kwargs["file_name"], "guide.md")

    def test_upload_document_returns_pending_payload_and_queues_processing(self) -> None:
        user = User.objects.create_user(email="staff-upload@example.com", is_staff=True)
        service = KnowledgeBaseService()

        with (
            mock.patch.object(service.object_storage, "upload_bytes") as upload_mock,
            mock.patch.object(service, "_submit_document_processing", return_value=True) as submit_mock,
        ):
            payload = service.upload_document(
                file_name="guide.md",
                content_type="text/markdown",
                file_bytes=b"# title\ncontent",
                actor=user,
            )

        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["status_detail"], "文件已上传，等待解析")
        self.assertEqual(payload["progress_percent"], 5)
        self.assertEqual(payload["file_size_bytes"], len(b"# title\ncontent"))
        upload_mock.assert_called_once()
        submit_mock.assert_called_once()

    def test_knowledge_overview_aggregates_document_counts_and_sizes(self) -> None:
        user = User.objects.create_user(email="staff-overview-db@example.com", is_staff=True)
        service = KnowledgeBaseService()
        base = service._ensure_default_base(actor=user)
        service._ensure_default_base(actor=user)

        service_document_defaults = {
            "knowledge_base": base,
            "mime_type": "text/markdown",
        }

        KnowledgeDocumentRecord.objects.create(
            title="文档 1",
            file_name="doc-1.md",
            object_key="knowledge/kb/doc-1.md",
            file_size_bytes=1024,
            status=KnowledgeDocumentRecord.STATUS_READY,
            **service_document_defaults,
        )
        KnowledgeDocumentRecord.objects.create(
            title="文档 2",
            file_name="doc-2.md",
            object_key="knowledge/kb/doc-2.md",
            file_size_bytes=2048,
            status=KnowledgeDocumentRecord.STATUS_FAILED,
            **service_document_defaults,
        )

        payload = service.get_overview_payload(actor=user)

        self.assertEqual(payload["document_count"], 2)
        self.assertEqual(payload["indexed_document_count"], 1)
        self.assertEqual(payload["total_file_size_bytes"], 3072)
        self.assertEqual(payload["total_file_size_label"], "3.0 KB")

    def test_safe_filename_keeps_chinese_name(self) -> None:
        self.assertEqual(_safe_filename("北京资料.md"), "北京资料.md")
        self.assertEqual(_safe_filename(" /tmp/旅行 计划.txt "), "-tmp-旅行 计划.txt")

    @mock.patch("planner.services.knowledge_base_service.PdfReader")
    def test_extract_document_text_reads_pdf_pages(self, pdf_reader_mock) -> None:
        pdf_reader_mock.return_value.pages = [
            mock.Mock(extract_text=mock.Mock(return_value="第一页内容")),
            mock.Mock(extract_text=mock.Mock(return_value="第二页内容")),
        ]

        service = KnowledgeBaseService()
        text = service._extract_document_text(file_name="guide.pdf", file_bytes=b"%PDF-1.4")

        self.assertIn("第一页内容", text)
        self.assertIn("第二页内容", text)

    @mock.patch("planner.services.knowledge_base_service.PdfReader")
    def test_extract_document_text_rejects_image_only_pdf(self, pdf_reader_mock) -> None:
        pdf_reader_mock.return_value.pages = [
            mock.Mock(extract_text=mock.Mock(return_value="")),
        ]

        service = KnowledgeBaseService()

        with self.assertRaisesMessage(ValueError, "带文本层的 pdf"):
            service._extract_document_text(file_name="scan.pdf", file_bytes=b"%PDF-1.4")

    def test_knowledge_document_delete_returns_204(self) -> None:
        user = User.objects.create_user(email="staff4@example.com", is_staff=True)
        request = self.factory.delete("/api/knowledge/documents/doc-1/")
        force_authenticate(request, user=user)

        with mock.patch(
            "planner.api.views.knowledge_base_service.delete_document",
            return_value=True,
        ):
            response = knowledge_document_view(request, "doc-1")

        self.assertEqual(response.status_code, 204)

    def test_knowledge_document_retry_returns_payload(self) -> None:
        user = User.objects.create_user(email="staff6@example.com", is_staff=True)
        request = self.factory.post("/api/knowledge/documents/doc-1/retry/", data=json.dumps({}), content_type="application/json")
        force_authenticate(request, user=user)

        with mock.patch(
            "planner.api.views.knowledge_base_service.retry_document",
            return_value={
                "document_id": "doc-1",
                "status": "pending",
                "status_detail": "已重新加入解析队列",
                "progress_percent": 5,
                "chunk_count": 0,
            },
        ) as retry_mock:
            response = knowledge_document_retry_view(request, "doc-1")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["document_id"], "doc-1")
        retry_mock.assert_called_once_with("doc-1")

    def test_knowledge_reindex_returns_payload(self) -> None:
        user = User.objects.create_user(email="staff5@example.com", is_staff=True)
        request = self.factory.post("/api/knowledge/reindex/", data=json.dumps({}), content_type="application/json")
        force_authenticate(request, user=user)

        with mock.patch(
            "planner.api.views.knowledge_base_service.reindex_all",
            return_value={"queued": 2, "document_count": 2},
        ):
            response = knowledge_reindex_view(request)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["queued"], 2)

    def test_create_chat_session_returns_201(self) -> None:
        response = chat_sessions_view(self.factory.post("/api/chat/sessions/"))
        self.assertEqual(response.status_code, 201)
        self.assertIn("session_id", response.data)
        self.assertIn("guest_token", response.data)

    def test_create_chat_turn_rejects_empty_payload(self) -> None:
        session = chat_sessions_view(self.factory.post("/api/chat/sessions/")).data
        request = self.factory.post(
            f"/api/chat/sessions/{session['session_id']}/messages/",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_X_GUEST_TOKEN=session["guest_token"],
        )

        response = create_chat_turn_view(request, session["session_id"])

        self.assertEqual(response.status_code, 400)

    def test_create_chat_turn_accepts_valid_payload(self) -> None:
        session = chat_sessions_view(self.factory.post("/api/chat/sessions/")).data
        request = self.factory.post(
            f"/api/chat/sessions/{session['session_id']}/messages/",
            data=json.dumps({"message": "预算 3000，两天，去上海博物馆和外滩"}),
            content_type="application/json",
            HTTP_X_GUEST_TOKEN=session["guest_token"],
        )

        response = create_chat_turn_view(request, session["session_id"])

        self.assertEqual(response.status_code, 202)
        self.assertIn("turn_id", response.data)
        self.assertEqual(response.data["phase"], "queued")
        self.assertTrue(response.data["stream_supported"])

    def test_create_chat_turn_stream_returns_sse_events(self) -> None:
        session = chat_sessions_view(self.factory.post("/api/chat/sessions/")).data
        queued_turn = ChatTurn(
            turn_id="turn-stream",
            session_id=session["session_id"],
            status="queued",
            user_message=ChatMessage(
                message_id="m1",
                role="user",
                content="帮我规划上海两日游",
                turn_id="turn-stream",
            ),
        )
        completed_turn = ChatTurn(
            turn_id="turn-stream",
            session_id=session["session_id"],
            status="completed",
            user_message=queued_turn.user_message,
            result=TripPlanOutput(
                status="success",
                plan_state="draft",
                trip_summary="上海两日游路线已生成。",
            ),
            assistant_message=ChatMessage(
                message_id="m2",
                role="assistant",
                content="已为你生成上海两日游路线。",
                turn_id="turn-stream",
                message_type="result",
            ),
        )
        request = self.factory.post(
            f"/api/chat/sessions/{session['session_id']}/messages/stream/",
            data=json.dumps({"message": "帮我规划上海两日游"}),
            content_type="application/json",
            HTTP_X_GUEST_TOKEN=session["guest_token"],
            HTTP_ACCEPT="text/event-stream",
        )

        with mock.patch(
            "planner.api.views.planner_service.submit_chat_turn",
            return_value=queued_turn,
        ), mock.patch(
            "planner.api.views.planner_service.get_chat_turn",
            side_effect=[queued_turn, completed_turn],
        ), mock.patch("planner.api.views.time.sleep", return_value=None):
            response = create_chat_turn_stream_view(request, session["session_id"])
            payload = b"".join(
                chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
                for chunk in response.streaming_content
            ).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertIn("event: turn.created", payload)
        self.assertIn("event: turn.result", payload)
        self.assertIn("event: message.delta", payload)
        self.assertIn("event: turn.complete", payload)

    def test_chat_session_view_returns_404_for_missing_session(self) -> None:
        response = chat_session_view(self.factory.get("/api/chat/sessions/missing/"), "missing")
        self.assertEqual(response.status_code, 404)

    def test_chat_turn_view_returns_model_payload(self) -> None:
        assistant_message = ChatMessage(
            message_id="message-2",
            role="assistant",
            content="路线草案已生成",
            turn_id="turn-1",
            message_type="result",
        )
        fake_turn = ChatTurn(
            turn_id="turn-1",
            session_id="session-1",
            status="completed",
            user_message=ChatMessage(
                message_id="message-1",
                role="user",
                content="帮我规划上海两日游",
                turn_id="turn-1",
            ),
            assistant_message=assistant_message,
        )
        with mock.patch(
            "planner.api.views.planner_service.get_chat_turn",
            return_value=fake_turn,
        ):
            response = chat_turn_view(
                self.factory.get("/api/chat/sessions/session-1/turns/turn-1/"),
                "session-1",
                "turn-1",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["turn_id"], "turn-1")
        self.assertEqual(response.data["phase"], "completed")
        self.assertTrue(response.data["stream_supported"])

    def test_auth_me_returns_unauthenticated_without_token(self) -> None:
        response = auth_me_view(self.factory.get("/api/auth/me/"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["authenticated"])
        self.assertIn("asset_summary", response.data)
        self.assertEqual(response.data["asset_summary"]["session_count"], 0)

    def test_auth_me_returns_asset_summary_for_authenticated_user(self) -> None:
        user = User.objects.create_user(email="summary@example.com")
        TripPlanRecord.objects.create(
            owner=user,
            title="上海草案",
            status="draft",
            version=1,
            constraints_snapshot={"destination": "上海", "days": 2},
            result_snapshot={"status": "success", "trip_summary": "上海两日游"},
        )
        session_response = chat_sessions_view(self.factory.post("/api/chat/sessions/"))
        session_id = session_response.data["session_id"]
        from planner.models import ChatSessionRecord

        ChatSessionRecord.objects.filter(session_id=session_id).update(owner=user, guest_token=None)

        request = self.factory.get("/api/auth/me/")
        force_authenticate(request, user=user)

        response = auth_me_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["authenticated"])
        self.assertEqual(response.data["asset_summary"]["session_count"], 1)
        self.assertEqual(response.data["asset_summary"]["plan_count"], 1)
        self.assertEqual(response.data["asset_summary"]["plan_status_counts"]["draft"], 1)

    def test_send_auth_code_uses_service(self) -> None:
        request = self.factory.post(
            "/api/auth/codes/",
            data=json.dumps({"email": "user@example.com"}),
            content_type="application/json",
        )
        with mock.patch(
            "planner.api.views.auth_service.send_login_code",
            return_value={"message": "验证码已发送。", "debug_code": "123456"},
        ) as send_login_code:
            response = send_auth_code_view(request)

        self.assertEqual(response.status_code, 202)
        send_login_code.assert_called_once()

    def test_send_auth_code_returns_503_when_delivery_fails(self) -> None:
        from planner.services.auth_service import AuthDeliveryError

        request = self.factory.post(
            "/api/auth/codes/",
            data=json.dumps({"email": "user@example.com"}),
            content_type="application/json",
        )
        with mock.patch(
            "planner.api.views.auth_service.send_login_code",
            side_effect=AuthDeliveryError("验证码发送失败，请稍后重试。"),
        ):
            response = send_auth_code_view(request)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "auth_delivery_failed")

    def test_send_auth_code_rejects_invalid_email(self) -> None:
        request = self.factory.post(
            "/api/auth/codes/",
            data=json.dumps({"email": "invalid-email"}),
            content_type="application/json",
        )

        response = send_auth_code_view(request)

        self.assertEqual(response.status_code, 400)

    def test_verify_auth_code_uses_service(self) -> None:
        request = self.factory.post(
            "/api/auth/login/verify/",
            data=json.dumps({"email": "user@example.com", "code": "123456"}),
            content_type="application/json",
        )
        with mock.patch(
            "planner.api.views.auth_service.verify_login_code",
            return_value={
                "access_token": "access",
                "refresh_token": "refresh",
                "user": {"id": "1", "email": "user@example.com", "display_name": "user"},
            },
        ) as verify_login_code:
            response = verify_auth_code_view(request)

        self.assertEqual(response.status_code, 200)
        verify_login_code.assert_called_once()

    def test_verify_auth_code_tolerates_missing_assistant_tables_during_guest_claim(self) -> None:
        from planner.services.auth_service import auth_service

        auth_service.state_store.store_login_code(
            email="migrate-safe@example.com",
            code="123456",
            request_ip="127.0.0.1",
            now=timezone.now(),
        )
        request = self.factory.post(
            "/api/auth/login/verify/",
            data=json.dumps(
                {
                    "email": "migrate-safe@example.com",
                    "code": "123456",
                    "guest_token": "guest-token-1",
                }
            ),
            content_type="application/json",
        )

        with mock.patch(
            "planner.services.assistant_store.AssistantConversationRecord.objects.filter",
            side_effect=ProgrammingError(
                '(1146, "Table \'trip_assistant.planner_assistant_conversation\' doesn\'t exist")'
            ),
        ):
            response = verify_auth_code_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.data)

    def test_password_login_uses_service(self) -> None:
        request = self.factory.post(
            "/api/auth/login/password/",
            data=json.dumps({"email": "user@example.com", "password": "secret123"}),
            content_type="application/json",
        )
        with mock.patch(
            "planner.api.views.auth_service.login_with_password",
            return_value={
                "access_token": "access",
                "refresh_token": "refresh",
                "user": {
                    "id": "1",
                    "email": "user@example.com",
                    "display_name": "user",
                    "has_password": True,
                },
            },
        ) as password_login:
            response = password_login_view(request)

        self.assertEqual(response.status_code, 200)
        password_login.assert_called_once()

    def test_set_password_uses_service(self) -> None:
        user = User.objects.create_user(email="user@example.com")
        request = self.factory.post(
            "/api/auth/password/",
            data=json.dumps({"current_password": "", "new_password": "secret123"}),
            content_type="application/json",
        )
        force_authenticate(request, user=user)
        with mock.patch(
            "planner.api.views.auth_service.set_password",
            return_value={"message": "密码已设置。"},
        ) as set_password:
            response = set_password_view(request)

        self.assertEqual(response.status_code, 200)
        set_password.assert_called_once()

    def test_chat_sessions_list_includes_summary_fields(self) -> None:
        created = chat_sessions_view(self.factory.post("/api/chat/sessions/")).data
        request = self.factory.get(
            "/api/chat/sessions/",
            HTTP_X_GUEST_TOKEN=created["guest_token"],
        )

        response = chat_sessions_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["recent_session_id"], created["session_id"])
        self.assertIn("idle", response.data["status_counts"])

    def test_chat_session_rename_rejects_blank_title(self) -> None:
        created = chat_sessions_view(self.factory.post("/api/chat/sessions/")).data
        request = self.factory.patch(
            f"/api/chat/sessions/{created['session_id']}/",
            data=json.dumps({"title": "   "}),
            content_type="application/json",
            HTTP_X_GUEST_TOKEN=created["guest_token"],
        )

        response = chat_session_view(request, created["session_id"])

        self.assertEqual(response.status_code, 400)

    def test_save_trip_plan_rejects_invalid_status(self) -> None:
        user = User.objects.create_user(email="planner@example.com")
        created = chat_sessions_view(self.factory.post("/api/chat/sessions/")).data
        from planner.models import ChatSessionRecord

        ChatSessionRecord.objects.filter(session_id=created["session_id"]).update(
            owner=user,
            guest_token=None,
            latest_result=TripPlanOutput(
                status="success",
                plan_state="draft",
                trip_summary="上海两日游草案",
            ).model_dump(mode="json"),
        )
        request = self.factory.post(
            f"/api/chat/sessions/{created['session_id']}/plans/",
            data=json.dumps({"status": "archived"}),
            content_type="application/json",
        )
        force_authenticate(request, user=user)

        response = save_trip_plan_view(request, created["session_id"])

        self.assertEqual(response.status_code, 400)

    def test_trip_plans_list_includes_count_and_status_summary(self) -> None:
        user = User.objects.create_user(email="plans@example.com")
        TripPlanRecord.objects.create(
            owner=user,
            title="上海草案",
            status="draft",
            version=1,
            constraints_snapshot={"destination": "上海", "days": 2},
            result_snapshot={"status": "success", "trip_summary": "上海两日游"},
        )
        TripPlanRecord.objects.create(
            owner=user,
            title="杭州终版",
            status="final",
            version=1,
            constraints_snapshot={"destination": "杭州", "days": 3},
            result_snapshot={"status": "success", "trip_summary": "杭州三日游"},
        )
        request = self.factory.get("/api/trip-plans/")
        force_authenticate(request, user=user)

        response = trip_plans_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["status_counts"]["draft"], 1)
        self.assertEqual(response.data["status_counts"]["final"], 1)

    def test_save_plan_from_run_returns_201(self) -> None:
        user = User.objects.create_user(email="run-save@example.com")
        plan_request = self.factory.post(
            "/api/plans/",
            data=json.dumps(
                {
                    "destination": "Hangzhou",
                    "days": 2,
                    "budget": 2000,
                }
            ),
            content_type="application/json",
        )
        force_authenticate(plan_request, user=user)
        plan_response = plan_trip_view(plan_request)

        from planner.models import PlanningJob

        PlanningJob.objects.filter(job_id=plan_response.data["run_id"]).update(
            result_payload={
                "status": "success",
                "plan_state": "draft",
                "trip_summary": "杭州两日游草案",
            }
        )

        save_request = self.factory.post(
            f"/api/plans/{plan_response.data['run_id']}/save/",
            data=json.dumps({"status": "draft"}),
            content_type="application/json",
        )
        force_authenticate(save_request, user=user)

        response = save_run_plan_view(save_request, plan_response.data["run_id"])

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "draft")


if __name__ == "__main__":
    import unittest

    unittest.main()
