import os
import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trip_planner_backend.settings")

from planner.domain.schemas import ChatSession, ChatTurnCreateRequest, TripPlanningRequest
from planner.graph.nodes import PlanningNodes
from planner.graph.workflow import TripPlannerWorkflow
from planner.integrations.qwen import QwenPlannerClient
from planner.services.live_data import LiveDataService
from planner.services.planning_context import build_chat_context
from planner.services.route_directions import RouteDirectionsService
from planner.services.runtime_config import ProviderConfig, QwenConfig, RuntimeConfig


class WorkflowTests(TestCase):
    def setUp(self) -> None:
        self.config = RuntimeConfig(
            default_city="Shanghai",
            cache_ttl_seconds=60,
            rate_limit_seconds=0.0,
            qwen=QwenConfig(
                api_key=None,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model="qwen3.5-plus",
                timeout_seconds=2.0,
                temperature=0.3,
                enable_thinking=False,
            ),
            amap=ProviderConfig("amap", "https://example.com/amap", None, 2.0, 0),
            baidu=ProviderConfig("baidu", "https://example.com/baidu", None, 2.0, 0),
        )
        self.workflow = TripPlannerWorkflow(
            PlanningNodes(
                live_data_service=LiveDataService(self.config),
                model_client=QwenPlannerClient(self.config.qwen),
                route_directions_service=RouteDirectionsService(self.config),
            )
        )

    def test_sequential_workflow_returns_structured_output(self) -> None:
        result = self.workflow.run(
            TripPlanningRequest(
                destination="Shanghai",
                days=3,
                budget=3000,
                interests=["museum", "waterfront"],
            ),
        )
        self.assertIn(result.status, {"success", "clarification"})
        self.assertTrue(result.trip_summary)
        self.assertIn(result.plan_state, {"draft", "final", "clarification"})

    def test_chat_context_returns_clarification_for_incomplete_request(self) -> None:
        context = build_chat_context(
            ChatSession(session_id="session-1"),
            ChatTurnCreateRequest(message="想在上海边走边逛一天，不要太赶"),
        )

        result = self.workflow.run_context(context)

        self.assertEqual(result.status, "clarification")
        self.assertEqual(result.plan_state, "clarification")
        self.assertEqual(result.confirmed_constraints.destination, "上海")
        self.assertEqual(result.confirmed_constraints.days, 1)
        self.assertTrue(result.clarification_questions)

    def test_chat_context_keeps_preferences_out_of_removed_pois(self) -> None:
        context = build_chat_context(
            ChatSession(session_id="session-1"),
            ChatTurnCreateRequest(message="想在上海边走边逛一天，不要太赶，偏爱咖啡馆和江景"),
        )

        self.assertEqual(context.confirmed_constraints.destination, "上海")
        self.assertEqual(context.confirmed_constraints.days, 1)
        self.assertEqual(context.confirmed_constraints.pace_preference, "relaxed")
        self.assertEqual(context.confirmed_constraints.avoid_pois, [])
        self.assertEqual(context.confirmed_constraints.must_visit_pois, [])
        self.assertIn("咖啡馆", context.confirmed_constraints.interests)
        self.assertIn("江景", context.confirmed_constraints.interests)

    def test_chat_context_answers_general_question_in_general_mode(self) -> None:
        context = build_chat_context(
            ChatSession(session_id="session-1"),
            ChatTurnCreateRequest(message="帮我解释一下为什么海边城市春天容易起雾"),
        )

        result = self.workflow.run_context(context)

        self.assertEqual(result.assistant_mode, "general")
        self.assertEqual(result.status, "success")
        self.assertFalse(result.daily_itinerary)

    def test_workflow_logs_qwen_fallback_reason_when_api_key_missing(self) -> None:
        with self.assertLogs("planner.integrations.qwen", level="WARNING") as captured:
            result = self.workflow.run(
                TripPlanningRequest(
                    destination="Shanghai",
                    days=2,
                    budget=2000,
                    interests=["museum"],
                ),
            )

        self.assertIn(result.status, {"success", "clarification"})
        self.assertTrue(
            any("reason=missing_api_key" in message for message in captured.output)
        )

    def test_qwen_logs_when_degraded_status_is_derived_from_upstream_provider_state(self) -> None:
        client = QwenPlannerClient(self.config.qwen)

        with self.assertLogs("planner.integrations.qwen", level="WARNING") as captured:
            result = client._from_llm_json(
                request=TripPlanningRequest(
                    destination="Shanghai",
                    days=2,
                    budget=2000,
                    interests=["museum"],
                ),
                raw={
                    "status": "success",
                    "trip_summary": "行程已经生成。",
                    "daily_itinerary": [],
                    "budget_breakdown": {},
                    "transportation": [],
                    "recommendations": [],
                    "warnings": [],
                    "route_overview": {},
                    "alternatives": [],
                    "clarification_questions": [],
                },
                attractions=[],
                foods=[],
                hotels=[],
                assumptions=["上游数据源存在降级。"],
                source_references=[],
                degraded=True,
                confirmed_constraints=None,
                conversation_summary="",
                assistant_mode="travel",
                suggested_clarification_questions=[],
            )

        self.assertEqual(result.status, "success")
        self.assertTrue(
            any(
                "reason=upstream_provider_degraded" in message
                for message in captured.output
            )
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
