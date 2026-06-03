from __future__ import annotations

import json
import shlex
import tempfile
from pathlib import Path

import requests
from django.core.management.base import BaseCommand

from planner.domain.schemas import TripPlanningRequest, WorkflowState
from planner.graph.nodes import PlanningNodes
from planner.integrations.qwen import QwenPlannerClient
from planner.services.live_data import LiveDataService
from planner.services.runtime_config import load_runtime_config


class Command(BaseCommand):
    help = "Export the real Qwen request body used by the planner and print an equivalent curl command."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--destination", required=True)
        parser.add_argument("--days", type=int, required=True)
        parser.add_argument("--budget", type=float, default=None)
        parser.add_argument("--city", default=None)
        parser.add_argument("--interest", action="append", default=[])
        parser.add_argument("--food-preference", action="append", default=[])
        parser.add_argument("--hotel-preference", action="append", default=[])
        parser.add_argument("--constraint", action="append", default=[])
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Post the exported body directly to Qwen and print the HTTP status and a short response preview.",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=None,
            help="Override the request timeout in seconds for direct execution.",
        )

    def handle(self, *args, **options) -> None:
        config = load_runtime_config()
        request = TripPlanningRequest(
            destination=options["destination"],
            days=options["days"],
            budget=options["budget"],
            city=options["city"],
            interests=options["interest"],
            food_preferences=options["food_preference"],
            hotel_preferences=options["hotel_preference"],
            constraints=options["constraint"],
        )

        nodes = PlanningNodes(
            live_data_service=LiveDataService(config),
            model_client=QwenPlannerClient(config.qwen),
        )
        state = WorkflowState(request=request)
        state, _ = nodes.normalize_input(state)
        state, _ = nodes.fetch_live_data(state)
        state, _ = nodes.validate_live_data(state)

        degraded = any(
            provider.status != "success" for provider in state.live_data.provider_statuses
        )
        client = QwenPlannerClient(config.qwen)
        body = client.build_chat_request_body(
            request=state.normalized_request or state.request,
            attractions=state.live_data.pois,
            foods=state.live_data.foods,
            hotels=state.live_data.hotels,
            assumptions=state.assumptions,
            degraded=degraded,
        )

        temp = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix="qwen-request-",
            delete=False,
        )
        body_path = Path(temp.name)
        with temp:
            json.dump(body, temp, ensure_ascii=False, indent=2)

        endpoint = client.chat_completions_url()
        curl_command = self._build_curl_command(endpoint, body_path)

        self.stdout.write(f"Request body written to: {body_path}")
        self.stdout.write(
            "Live data counts: "
            f"pois={len(state.live_data.pois)}, "
            f"foods={len(state.live_data.foods)}, "
            f"hotels={len(state.live_data.hotels)}"
        )
        self.stdout.write(
            "Provider statuses: "
            + json.dumps(
                [
                    {
                        "provider": item.provider,
                        "status": item.status,
                        "message": item.message,
                    }
                    for item in state.live_data.provider_statuses
                ],
                ensure_ascii=False,
            )
        )
        self.stdout.write(
            "Assumptions: " + json.dumps(state.assumptions, ensure_ascii=False)
        )
        self.stdout.write("Equivalent curl:")
        self.stdout.write(curl_command)

        if options["execute"]:
            try:
                response = requests.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {config.qwen.api_key or ''}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=options["timeout"] or config.qwen.timeout_seconds,
                )
                preview = response.text[:800]
                self.stdout.write(f"HTTP {response.status_code}")
                self.stdout.write(preview)
            except requests.RequestException as exc:
                self.stdout.write(f"Request execution failed: {exc}")

    @staticmethod
    def _build_curl_command(endpoint: str, body_path: Path) -> str:
        return (
            "curl -X POST "
            + shlex.quote(endpoint)
            + " "
            + '-H "Content-Type: application/json" '
            + '-H "Authorization: Bearer $DASHSCOPE_API_KEY" '
            + f"--data @{shlex.quote(str(body_path))}"
        )
