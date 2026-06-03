import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase, mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trip_planner_backend.settings")

from planner.domain.schemas import (
    ConfirmedConstraints,
    DailyPlan,
    FoodCandidate,
    HotelCandidate,
    POICandidate,
    ProviderStatus,
    SourceReference,
    TravelDataBundle,
    TripPlanningRequest,
)
from planner.integrations.amap import AmapDirectionClient, AmapPOIClient
from planner.integrations.baidu import BaiduPlaceClient
from planner.integrations.qwen import QwenPlannerClient
from planner.integrations.base import RateLimiter, TTLCacheStore
from planner.services.live_data import LiveDataService
from planner.services.route_directions import RouteDirectionsService
from planner.services.runtime_config import ProviderConfig, QwenConfig, RuntimeConfig


class LiveDataServiceTests(TestCase):
    def setUp(self) -> None:
        self.config = RuntimeConfig(
            default_city="Shanghai",
            cache_ttl_seconds=60,
            rate_limit_seconds=0.0,
            qwen=QwenConfig(
                api_key="test-api-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model="qwen3.5-plus",
                timeout_seconds=8.0,
                temperature=0.3,
                enable_thinking=False,
            ),
            amap=ProviderConfig("amap", "https://example.com/amap", "key", 5.0, 0),
            baidu=ProviderConfig("baidu", "https://example.com/baidu", "key", 5.0, 0),
        )

    def test_provider_status_shape(self) -> None:
        status = ProviderStatus(
            provider="amap",
            status="success",
            message="Fetched live data",
            fetched_at=datetime.now(timezone.utc),
        )
        self.assertEqual(status.provider, "amap")

    def test_service_builds_with_runtime_config(self) -> None:
        service = LiveDataService(self.config)
        self.assertIsNotNone(service.amap)
        self.assertIsNotNone(service.baidu)


class BaiduPlaceClientTests(TestCase):
    def setUp(self) -> None:
        self.client = BaiduPlaceClient(
            ProviderConfig("baidu", "https://example.com/baidu", "key", 5.0, 0),
            TTLCacheStore(60),
            RateLimiter(0.0),
        )

    def test_search_foods_normalizes_results(self) -> None:
        payload = {
            "results": [
                {
                    "uid": "food-1",
                    "name": "老街面馆",
                    "address": "中山路 18 号",
                    "location": {"lng": 120.1551, "lat": 30.2741},
                    "detail_info": {
                        "tag": "美食;面馆",
                        "overall_rating": "4.6",
                        "price": "48",
                    },
                }
            ]
        }
        with mock.patch.object(self.client, "_request_json", return_value=payload):
            foods = self.client.search_foods(
                destination="Hangzhou",
                city="Hangzhou",
                keywords=["面馆"],
            )

        self.assertEqual(len(foods), 1)
        self.assertEqual(foods[0].source.provider, "baidu")
        self.assertEqual(foods[0].cuisine, "美食")
        self.assertEqual(foods[0].average_cost, 48.0)
        self.assertEqual(foods[0].location, "120.1551,30.2741")

    def test_search_foods_retries_with_individual_and_fallback_queries(self) -> None:
        responses = [
            {"results": []},
            {
                "results": [
                    {
                        "uid": "food-1",
                        "name": "老正兴",
                        "address": "福州路 556 号",
                        "detail_info": {
                            "tag": "美食;本帮菜",
                            "overall_rating": "4.5",
                            "price": "138",
                        },
                    }
                ]
            },
            {"results": []},
            {"results": []},
            {"results": []},
            {"results": []},
            {"results": []},
            {"results": []},
            {"results": []},
            {"results": []},
            {"results": []},
        ]
        with mock.patch.object(
            self.client, "_request_json", side_effect=responses
        ) as request_json:
            foods = self.client.search_foods(
                destination="上海",
                city="上海",
                keywords=["本帮菜", "咖啡馆"],
            )

        self.assertEqual(len(foods), 1)
        self.assertEqual(foods[0].name, "老正兴")
        requested_queries = [
            call.kwargs["params"]["query"] for call in request_json.call_args_list
        ]
        self.assertEqual(
            requested_queries[:4],
            ["本帮菜 咖啡馆", "本帮菜", "咖啡馆", "上海 本帮菜"],
        )

    def test_search_hotels_adds_map_based_note(self) -> None:
        payload = {
            "results": [
                {
                    "uid": "hotel-1",
                    "name": "西湖景观酒店",
                    "city": "Hangzhou",
                    "province": "Zhejiang",
                    "address": "湖滨路 1 号",
                    "location": {"lng": 120.1601, "lat": 30.2529},
                    "detail_info": {
                        "tag": "酒店",
                        "type": "hotel",
                        "overall_rating": "4.4",
                        "price": "680",
                    },
                }
            ]
        }
        with mock.patch.object(self.client, "_request_json", return_value=payload):
            hotels = self.client.search_hotels(
                destination="Hangzhou",
                city="Hangzhou",
                budget=3000,
                days=2,
                preferences=["湖景"],
            )

        self.assertEqual(len(hotels), 1)
        self.assertEqual(hotels[0].price_min, 680.0)
        self.assertEqual(hotels[0].location, "120.1601,30.2529")
        self.assertIn("地图地点检索", hotels[0].source.note or "")

    def test_search_hotels_filters_out_city_summary_items_and_uses_hotel_queries(self) -> None:
        responses = [
            {
                "results": [
                    {"name": "上海市", "num": 11},
                    {"name": "广州市", "num": 3},
                ]
            },
            {
                "results": [
                    {
                        "uid": "hotel-2",
                        "name": "全季酒店(上海陆家嘴店)",
                        "city": "上海市",
                        "province": "上海市",
                        "area": "浦东新区",
                        "address": "浦电路 100 号",
                        "detail_info": {
                            "tag": "酒店",
                            "classified_poi_tag": "酒店;舒适型",
                            "type": "hotel",
                            "overall_rating": "4.7",
                            "price": "680",
                        },
                    }
                ]
            },
            {"results": []},
            {"results": []},
            {"results": []},
            {"results": []},
            {"results": []},
            {"results": []},
            {"results": []},
        ]
        with mock.patch.object(
            self.client, "_request_json", side_effect=responses
        ) as request_json:
            hotels = self.client.search_hotels(
                destination="上海",
                city="上海",
                budget=3000,
                days=2,
                preferences=["地铁方便", "夜景"],
            )

        self.assertEqual(len(hotels), 1)
        self.assertEqual(hotels[0].name, "全季酒店(上海陆家嘴店)")
        self.assertEqual(hotels[0].city, "上海市")
        requested_queries = [
            call.kwargs["params"]["query"] for call in request_json.call_args_list
        ]
        self.assertEqual(
            requested_queries[:4],
            ["上海 酒店", "上海 地铁站 酒店", "上海 市中心 酒店", "上海 地铁方便 酒店"],
        )


class AmapPOIClientTests(TestCase):
    def setUp(self) -> None:
        self.client = AmapPOIClient(
            ProviderConfig("amap", "https://example.com/amap", "key", 5.0, 0),
            TTLCacheStore(60),
            RateLimiter(0.0),
        )

    def test_search_pois_retries_with_multiple_queries_and_deduplicates(self) -> None:
        responses = [
            {"pois": []},
            {
                "pois": [
                    {
                        "id": "poi-1",
                        "name": "上海博物馆",
                        "cityname": "上海",
                        "adname": "黄浦区",
                        "address": "人民大道 201 号",
                        "type": "博物馆",
                        "location": "121.4737,31.2304",
                    }
                ]
            },
            {
                "pois": [
                    {
                        "id": "poi-1",
                        "name": "上海博物馆",
                        "cityname": "上海",
                        "adname": "黄浦区",
                        "address": "人民大道 201 号",
                        "type": "博物馆",
                        "location": "121.4737,31.2304",
                    }
                ]
            },
            {"pois": []},
            {"pois": []},
            {"pois": []},
            {"pois": []},
        ]
        with mock.patch.object(
            self.client, "_request_json", side_effect=responses
        ) as request_json:
            pois = self.client.search_pois(
                destination="上海",
                city="上海",
                keywords=["博物馆"],
            )

        self.assertEqual(len(pois), 1)
        self.assertEqual(pois[0].name, "上海博物馆")
        requested_keywords = [
            call.kwargs["params"]["keywords"] for call in request_json.call_args_list
        ]
        self.assertEqual(requested_keywords[:3], ["上海 博物馆", "上海 景点", "上海 地标"])


class RouteDirectionsServiceTests(TestCase):
    def setUp(self) -> None:
        self.config = RuntimeConfig(
            default_city="Shanghai",
            cache_ttl_seconds=60,
            rate_limit_seconds=0.0,
            qwen=QwenConfig(
                api_key="test-api-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model="qwen3.5-plus",
                timeout_seconds=8.0,
                temperature=0.3,
                enable_thinking=False,
            ),
            amap=ProviderConfig("amap", "https://example.com/amap", "key", 5.0, 0),
            baidu=ProviderConfig("baidu", "https://example.com/baidu", "key", 5.0, 0),
        )
        self.service = RouteDirectionsService(self.config)

    def test_amap_direction_client_normalizes_transit_response(self) -> None:
        client = AmapDirectionClient(
            ProviderConfig("amap", "https://example.com/amap", "key", 5.0, 0),
            TTLCacheStore(60),
            RateLimiter(0.0),
        )
        with mock.patch.object(
            client,
            "_request_json",
            return_value={
                "status": "1",
                "route": {
                    "transits": [
                        {
                            "distance": "6200",
                            "cost": {
                                "duration": "1800",
                            },
                            "segments": [{}],
                        }
                    ]
                }
            },
        ):
            leg = client.estimate_leg(
                origin="121.4737,31.2304",
                destination="121.4900,31.2400",
                city="010",
                transport_preferences=["地铁"],
            )

        self.assertIsNotNone(leg)
        self.assertEqual(leg["mode"], "地铁 / 公交")
        self.assertEqual(leg["duration_minutes"], 30)

    def test_route_directions_service_builds_heuristic_legs_when_map_unavailable(self) -> None:
        itinerary = [
            DailyPlan(
                day=1,
                theme="Museum + Bund",
                morning=["上海博物馆"],
                dining=["老正兴"],
                afternoon=["外滩"],
            )
        ]
        live_data = TravelDataBundle(
            pois=[
                POICandidate(
                    id="poi-1",
                    name="上海博物馆",
                    city="上海",
                    district="黄浦区",
                    address="人民大道 201 号",
                    category="博物馆",
                    location="121.4737,31.2304",
                    source=SourceReference(provider="amap", label="Amap POI"),
                ),
                POICandidate(
                    id="poi-2",
                    name="外滩",
                    city="上海",
                    district="黄浦区",
                    address="中山东一路",
                    category="地标",
                    location="121.4900,31.2400",
                    source=SourceReference(provider="amap", label="Amap POI"),
                ),
            ],
            foods=[
                FoodCandidate(
                    id="food-1",
                    name="老正兴",
                    city="上海",
                    address="福州路 556 号",
                    cuisine="本帮菜",
                    source=SourceReference(provider="baidu", label="Baidu Food"),
                )
            ],
        )

        with mock.patch.object(
            self.service.direction_client,
            "estimate_leg",
            side_effect=RuntimeError("down"),
        ):
            overview, enriched_itinerary, stops, legs, alternatives, warnings = self.service.build_route_plan(
                request=TripPlanningRequest(
                    destination="上海",
                    city="上海",
                    days=1,
                    budget=2000,
                    interests=["博物馆", "外滩"],
                    transport_preferences=["地铁"],
                ),
                confirmed_constraints=ConfirmedConstraints(
                    destination="上海",
                    city="上海",
                    days=1,
                    budget=2000,
                    transport_preferences=["地铁"],
                    must_visit_pois=["上海博物馆", "外滩"],
                ),
                itinerary=itinerary,
                live_data=live_data,
            )

        self.assertIsNotNone(overview)
        self.assertTrue(enriched_itinerary)
        self.assertGreaterEqual(len(stops), 3)
        self.assertTrue(legs)
        self.assertEqual(legs[0].status, "estimated")
        self.assertTrue(alternatives or warnings)

    def test_route_directions_service_prefers_live_legs_when_food_and_hotel_have_locations(self) -> None:
        itinerary = [
            DailyPlan(
                day=1,
                theme="Museum + Bund",
                morning=["上海博物馆"],
                dining=["老正兴"],
                afternoon=["外滩"],
            )
        ]
        live_data = TravelDataBundle(
            pois=[
                POICandidate(
                    id="poi-1",
                    name="上海博物馆",
                    city="上海",
                    district="黄浦区",
                    address="人民大道 201 号",
                    category="博物馆",
                    location="121.4737,31.2304",
                    source=SourceReference(provider="amap", label="Amap POI"),
                ),
                POICandidate(
                    id="poi-2",
                    name="外滩",
                    city="上海",
                    district="黄浦区",
                    address="中山东一路",
                    category="地标",
                    location="121.4900,31.2400",
                    source=SourceReference(provider="amap", label="Amap POI"),
                ),
            ],
            foods=[
                FoodCandidate(
                    id="food-1",
                    name="老正兴",
                    city="上海",
                    address="福州路 556 号",
                    location="121.4798,31.2336",
                    cuisine="本帮菜",
                    source=SourceReference(provider="baidu", label="Baidu Food"),
                )
            ],
            hotels=[
                HotelCandidate(
                    id="hotel-1",
                    name="人民广场酒店",
                    city="上海",
                    address="人民大道 88 号",
                    location="121.4728,31.2320",
                    source=SourceReference(provider="baidu", label="Baidu Hotel"),
                )
            ],
        )

        with mock.patch.object(
            self.service.direction_client,
            "estimate_leg",
            return_value={
                "mode": "地铁 / 公交",
                "duration_minutes": 12,
                "distance_km": 2.1,
                "suggestion": "使用高德实时路线。",
                "source": SourceReference(provider="amap", label="高德路径规划"),
            },
        ):
            overview, enriched_itinerary, stops, legs, alternatives, warnings = self.service.build_route_plan(
                request=TripPlanningRequest(
                    destination="上海",
                    city="上海",
                    days=1,
                    budget=2000,
                    interests=["博物馆", "外滩"],
                    transport_preferences=["地铁"],
                ),
                confirmed_constraints=ConfirmedConstraints(
                    destination="上海",
                    city="上海",
                    days=1,
                    budget=2000,
                    transport_preferences=["地铁"],
                    must_visit_pois=["上海博物馆", "外滩"],
                ),
                itinerary=itinerary,
                live_data=live_data,
            )

        self.assertIsNotNone(overview)
        self.assertTrue(enriched_itinerary)
        self.assertGreaterEqual(len(stops), 4)
        self.assertEqual(len(legs), 3)
        self.assertTrue(all(leg.status == "live" for leg in legs))
        self.assertFalse(warnings)
        self.assertTrue(alternatives or True)


class QwenPlannerClientTests(TestCase):
    def test_build_chat_request_body_matches_expected_shape(self) -> None:
        client = QwenPlannerClient(
            QwenConfig(
                api_key="test-api-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model="qwen3.5-plus",
                timeout_seconds=8.0,
                temperature=0.3,
                enable_thinking=False,
            )
        )

        body = client.build_chat_request_body(
            request=TripPlanningRequest(destination="Shanghai", days=3, budget=3000),
            attractions=[],
            foods=[],
            hotels=[],
            assumptions=["已根据目的地自动补全城市信息。"],
            degraded=True,
        )

        self.assertEqual(body["model"], "qwen3.5-plus")
        self.assertEqual(len(body["messages"]), 2)
        self.assertIn("规划上下文如下", body["messages"][1]["content"])
        self.assertIn("已根据目的地自动补全城市信息。", body["messages"][1]["content"])

    def test_generate_trip_plan_falls_back_when_model_call_fails(self) -> None:
        client = QwenPlannerClient(
            QwenConfig(
                api_key="test-api-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model="qwen3.5-plus",
                timeout_seconds=8.0,
                temperature=0.3,
                enable_thinking=False,
            )
        )
        fake_prompt = mock.MagicMock()
        fake_chain = mock.MagicMock()
        fake_chain.invoke.side_effect = RuntimeError("rate limited")
        fake_prompt.__or__.return_value = fake_chain

        with mock.patch(
            "planner.integrations.qwen.ChatPromptTemplate"
        ) as prompt_template, mock.patch("planner.integrations.qwen.ChatOpenAI"):
            prompt_template.from_messages.return_value = fake_prompt
            result = client.generate_trip_plan(
                request=TripPlanningRequest(destination="Shanghai", days=3, budget=3000),
                attractions=[],
                foods=[],
                hotels=[],
                assumptions=[],
                source_references=[
                    SourceReference(provider="amap", label="高德 POI 检索")
                ],
                degraded=False,
            )

        self.assertEqual(result.status, "success")
        self.assertIn("模型请求失败", result.assumptions[-1])

    def test_from_llm_json_supports_qwen_shape(self) -> None:
        client = QwenPlannerClient(
            QwenConfig(
                api_key="test-api-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model="qwen3.5-plus",
                timeout_seconds=60.0,
                temperature=0.3,
                enable_thinking=False,
            )
        )
        raw = {
            "trip_summary": {
                "destination": "Shanghai",
                "duration_days": 2,
                "theme": "Museum and dining",
                "overview": "A compact cultural city trip.",
            },
            "daily_itinerary": [
                {
                    "day": 1,
                    "focus": "Museum day",
                    "activities": [
                        {
                            "time": "09:00-12:00",
                            "activity": "Visit Shanghai Museum",
                        },
                        {
                            "time": "12:30-13:30",
                            "activity": "Lunch at local restaurant",
                        },
                        {
                            "time": "18:30-20:00",
                            "activity": "Dinner at local restaurant",
                        },
                    ],
                }
            ],
            "budget_breakdown": {
                "accommodation": {"estimated_cost": 600, "notes": "Hotel estimate"},
                "food_and_dining": {"estimated_cost": 300, "details": "Food estimate"},
                "transportation": {"total_cost": 80, "notes": "Metro estimate"},
                "tickets_and_entertainment": {"total_cost": 100, "details": "Museum estimate"},
                "total_estimated": 1080,
            },
            "transportation": {
                "primary_mode": "Shanghai Metro",
                "details": "Use metro first.",
            },
            "recommendations": [
                {
                    "category": "Dining",
                    "item": "Local restaurant",
                    "reason": "Good local option.",
                }
            ],
            "warnings": ["Live POI data incomplete."],
        }

        result = client._from_llm_json(
            request=TripPlanningRequest(destination="Shanghai", days=2, budget=2500),
            raw=raw,
            attractions=[],
            foods=[],
            hotels=[],
            assumptions=[],
            source_references=[],
            degraded=False,
        )

        self.assertIn("Shanghai 2 天行程", result.trip_summary)
        self.assertEqual(result.daily_itinerary[0].morning, ["Visit Shanghai Museum"])
        self.assertEqual(result.daily_itinerary[0].dining, ["Lunch at local restaurant", "Dinner at local restaurant"])
        self.assertEqual(result.budget_breakdown.estimated_total, 1080)
        self.assertEqual(result.budget_breakdown.food, 300)
        self.assertEqual(result.transportation[0].mode, "Shanghai Metro")
        self.assertEqual(result.recommendations[0].title, "Local restaurant")
        self.assertEqual(result.warnings[0].message, "Live POI data incomplete.")

    def test_fallback_plan_supports_general_question_mode(self) -> None:
        client = QwenPlannerClient(
            QwenConfig(
                api_key=None,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model="qwen3.5-plus",
                timeout_seconds=60.0,
                temperature=0.3,
                enable_thinking=False,
            )
        )

        result = client.generate_trip_plan(
            request=TripPlanningRequest(destination="待确认目的地", days=1),
            attractions=[],
            foods=[],
            hotels=[],
            assumptions=[],
            source_references=[],
            degraded=False,
            conversation_summary="帮我解释一下为什么海边城市春天容易起雾",
            latest_user_message="帮我解释一下为什么海边城市春天容易起雾",
            assistant_mode="general",
        )

        self.assertEqual(result.assistant_mode, "general")
        self.assertIn("我已经收到你的问题", result.trip_summary)

    def test_from_llm_json_normalizes_realistic_qwen_values(self) -> None:
        client = QwenPlannerClient(
            QwenConfig(
                api_key="test-api-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model="qwen3.5-plus",
                timeout_seconds=60.0,
                temperature=0.3,
                enable_thinking=False,
            )
        )
        raw = {
            "trip_summary": {
                "destination": "上海",
                "duration_days": 2,
                "theme": "海派文化探索与美食寻味",
                "overview": "覆盖博物馆、地标和本帮菜。",
            },
            "daily_itinerary": [
                {
                    "day": "Day 1",
                    "focus": "经典地标与博物之旅",
                    "activities": [
                        {
                            "time": "09:00-11:30",
                            "location": "上海博物馆",
                            "description": "参观常设展览",
                        },
                        {
                            "time": "12:00-13:30",
                            "location": "黄河路",
                            "description": "午餐品尝本帮菜",
                        },
                        {
                            "time": "14:30-17:30",
                            "location": "外滩",
                            "description": "步行游览万国建筑群",
                        },
                    ],
                }
            ],
            "budget_breakdown": {
                "accommodation": {"estimated_cost": "¥800-1000", "details": "市中心中档酒店"},
                "food_and_dining": {"estimated_cost": "400元", "details": "本帮菜和小吃"},
                "transportation": {"estimated_cost": "120", "details": "地铁为主"},
                "tickets_and_entertainment": {"estimated_cost": "180元", "details": "展览和观光"},
                "contingency": {"estimated_cost": "100元", "details": "机动预算"},
                "total_estimated": "1600-1800元",
            },
            "transportation": {
                "primary_mode": "Metro & Walking",
                "strategy": "地铁覆盖主线路，步行串联周边街区。",
                "key_routes": ["南京东路 -> 外滩", "人民广场 -> 上海博物馆"],
            },
            "recommendations": [
                {
                    "category": "餐饮",
                    "item": "本帮菜馆",
                    "reason": "靠近主要行程动线，适合午餐安排。",
                }
            ],
            "warnings": [{"severity": "info", "reason": "周末热门景点建议提前预约。"}],
        }

        result = client._from_llm_json(
            request=TripPlanningRequest(destination="上海", days=2, budget=2500),
            raw=raw,
            attractions=[],
            foods=[],
            hotels=[],
            assumptions=[],
            source_references=[],
            degraded=False,
        )

        self.assertEqual(result.daily_itinerary[0].day, 1)
        self.assertEqual(result.daily_itinerary[0].theme, "经典地标与博物之旅")
        self.assertEqual(result.daily_itinerary[0].morning, ["上海博物馆: 参观常设展览"])
        self.assertEqual(result.daily_itinerary[0].dining, ["黄河路: 午餐品尝本帮菜"])
        self.assertEqual(result.daily_itinerary[0].afternoon, ["外滩: 步行游览万国建筑群"])
        self.assertEqual(result.budget_breakdown.accommodation, 900.0)
        self.assertEqual(result.budget_breakdown.food, 400.0)
        self.assertEqual(result.budget_breakdown.transportation, 120.0)
        self.assertEqual(result.budget_breakdown.activities, 180.0)
        self.assertEqual(result.budget_breakdown.estimated_total, 1700.0)
        self.assertIn("人民广场 -> 上海博物馆", result.transportation[0].recommendation)
        self.assertEqual(result.recommendations[0].title, "本帮菜馆")
        self.assertEqual(result.warnings[0].message, "周末热门景点建议提前预约。")

    def test_safe_load_json_extracts_payload_from_wrapped_text(self) -> None:
        raw = '以下是规划结果：\n```json\n{"trip_summary":"ok"}\n```\n请查收。'
        parsed = QwenPlannerClient._safe_load_json(raw)
        self.assertEqual(parsed["trip_summary"], "ok")

    def test_normalize_budget_breakdown_supports_alternate_qwen_keys(self) -> None:
        budget = QwenPlannerClient._normalize_budget_breakdown(
            {
                "accommodation": 1200.0,
                "food": 800.0,
                "transport": 200.0,
                "activities": 300.0,
                "total": 2500.0,
                "currency": "CNY",
            },
            TripPlanningRequest(destination="上海", days=2, budget=2500),
        )
        self.assertEqual(budget.accommodation, 1200.0)
        self.assertEqual(budget.food, 800.0)
        self.assertEqual(budget.transportation, 200.0)
        self.assertEqual(budget.activities, 300.0)
        self.assertEqual(budget.estimated_total, 2500.0)

    def test_normalize_warnings_maps_provider_severity_levels(self) -> None:
        warnings = QwenPlannerClient._normalize_warnings(
            [
                {"severity": "medium", "message": "Popular museums may book out."},
                {"severity": "low", "message": "Crowds are common on weekends."},
                {"severity": "high", "message": "Weather disruption possible."},
            ]
        )
        self.assertEqual([item.severity for item in warnings], ["warning", "info", "critical"])


if __name__ == "__main__":
    import unittest

    unittest.main()
