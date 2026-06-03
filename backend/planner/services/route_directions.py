from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Iterable

from planner.domain.exceptions import ProviderRequestError, ProviderUnavailableError
from planner.domain.schemas import (
    AlternativeRoute,
    ConfirmedConstraints,
    DailyPlan,
    FoodCandidate,
    HotelCandidate,
    POICandidate,
    RouteLeg,
    RouteOverview,
    RouteStop,
    SourceReference,
    TravelDataBundle,
    TripPlanningRequest,
    WarningItem,
)
from planner.integrations.amap import AmapDirectionClient
from planner.integrations.base import RateLimiter, build_cache_store
from planner.services.runtime_config import RuntimeConfig

logger = logging.getLogger(__name__)


class RouteDirectionsService:
    def __init__(self, config: RuntimeConfig) -> None:
        self.direction_client = AmapDirectionClient(
            config.amap,
            build_cache_store(config.cache_ttl_seconds, config.redis),
            RateLimiter(config.rate_limit_seconds),
        )

    def build_route_plan(
        self,
        *,
        request: TripPlanningRequest,
        confirmed_constraints: ConfirmedConstraints,
        itinerary: list[DailyPlan],
        live_data: TravelDataBundle,
    ) -> tuple[
        RouteOverview | None,
        list[DailyPlan],
        list[RouteStop],
        list[RouteLeg],
        list[AlternativeRoute],
        list[WarningItem],
    ]:
        enriched_itinerary = self._enrich_itinerary(
            request=request,
            confirmed_constraints=confirmed_constraints,
            itinerary=itinerary,
            live_data=live_data,
        )
        stops = self._build_route_stops(
            request=request,
            confirmed_constraints=confirmed_constraints,
            itinerary=enriched_itinerary,
            live_data=live_data,
        )
        if not stops:
            return None, enriched_itinerary, [], [], [], []

        overview = RouteOverview(
            headline=f"{request.destination} {request.days} 天路线草案",
            strategy=self._build_strategy_text(confirmed_constraints),
            pace=confirmed_constraints.pace_preference,
            total_stops=len(stops),
        )
        alternatives = self._build_alternatives(
            stops=stops,
            live_data=live_data,
            confirmed_constraints=confirmed_constraints,
        )

        warnings: list[WarningItem] = []
        legs: list[RouteLeg] = []
        route_statuses: set[str] = set()
        for previous, current in zip(stops, stops[1:]):
            if previous.day != current.day:
                continue
            leg = self._build_leg(
                request=request,
                confirmed_constraints=confirmed_constraints,
                origin=previous,
                destination=current,
            )
            legs.append(leg)
            route_statuses.add(leg.status)
        if "estimated" in route_statuses or "unavailable" in route_statuses:
            warnings.append(
                WarningItem(
                    severity="info",
                    message="部分路段为地图失败后的估算结果，请在出行前二次确认。",
                )
            )
        return overview, enriched_itinerary, stops, legs, alternatives, warnings

    def _build_route_stops(
        self,
        *,
        request: TripPlanningRequest,
        confirmed_constraints: ConfirmedConstraints,
        itinerary: list[DailyPlan],
        live_data: TravelDataBundle,
    ) -> list[RouteStop]:
        stops: list[RouteStop] = []
        hotel = live_data.hotels[0] if live_data.hotels else None

        if itinerary:
            for day_plan in itinerary:
                used_names_for_day: set[str] = set()
                order = 1
                if hotel is not None and day_plan.day == 1:
                    stop = self._candidate_to_stop(
                        candidate=hotel,
                        day=day_plan.day,
                        order=order,
                        kind="hotel",
                        time_slot="checkin",
                        fallback_description="每日起终点建议围绕酒店展开。",
                    )
                    if stop.name not in used_names_for_day:
                        stops.append(stop)
                        used_names_for_day.add(stop.name)
                        order += 1

                for time_slot, labels in (
                    ("morning", day_plan.morning),
                    ("afternoon", day_plan.afternoon),
                    ("dining", day_plan.dining),
                    ("evening", day_plan.evening),
                ):
                    for candidate_label in self._limit_slot_labels(labels, time_slot):
                        stop = self._match_label_to_stop(
                            label=candidate_label,
                            day=day_plan.day,
                            order=order,
                            time_slot=time_slot,
                            live_data=live_data,
                            confirmed_constraints=confirmed_constraints,
                        )
                        if stop.name in used_names_for_day and time_slot != "dining":
                            continue
                        stops.append(stop)
                        used_names_for_day.add(stop.name)
                        order += 1

        if not stops:
            stops.extend(
                self._build_fallback_stops(
                    request=request,
                    live_data=live_data,
                    confirmed_constraints=confirmed_constraints,
                )
            )

        avoid = confirmed_constraints.avoid_pois
        if not avoid:
            return stops
        return [
            stop
            for stop in stops
            if not any(
                phrase in stop.name or stop.name in phrase
                for phrase in confirmed_constraints.avoid_pois
            )
        ]

    def _build_fallback_stops(
        self,
        *,
        request: TripPlanningRequest,
        live_data: TravelDataBundle,
        confirmed_constraints: ConfirmedConstraints,
    ) -> list[RouteStop]:
        stops: list[RouteStop] = []
        hotel = live_data.hotels[0] if live_data.hotels else None
        poi_count = len(live_data.pois)
        food_count = len(live_data.foods)
        for day in range(1, request.days + 1):
            order = 1
            if hotel is not None and day == 1:
                stops.append(
                    self._candidate_to_stop(
                        candidate=hotel,
                        day=day,
                        order=order,
                        kind="hotel",
                        time_slot="checkin",
                        fallback_description="建议围绕酒店展开第一天动线。",
                    )
                )
                order += 1

            if poi_count:
                morning_poi = live_data.pois[((day - 1) * 2) % poi_count]
                stops.append(
                    self._candidate_to_stop(
                        candidate=morning_poi,
                        day=day,
                        order=order,
                        kind="poi",
                        time_slot="morning",
                        fallback_description="根据实时候选点自动补齐上午行程。",
                    )
                )
                order += 1

                if poi_count > 1:
                    afternoon_poi = live_data.pois[(((day - 1) * 2) + 1) % poi_count]
                    if afternoon_poi.name != morning_poi.name:
                        stops.append(
                            self._candidate_to_stop(
                                candidate=afternoon_poi,
                                day=day,
                                order=order,
                                kind="poi",
                                time_slot="afternoon",
                                fallback_description="根据实时候选点自动补齐下午行程。",
                            )
                        )
                        order += 1

            if food_count:
                food = live_data.foods[(day - 1) % food_count]
                stops.append(
                    self._candidate_to_stop(
                        candidate=food,
                        day=day,
                        order=order,
                        kind="food",
                        time_slot="dining",
                        fallback_description="根据实时餐饮候选自动补齐用餐安排。",
                    )
                )
        if confirmed_constraints.must_visit_pois and not stops:
            for phrase in confirmed_constraints.must_visit_pois[:3]:
                stops.append(
                    RouteStop(
                        stop_id=f"manual-{order}",
                        day=1,
                        order=order,
                        name=phrase,
                        kind="poi",
                        time_slot="all_day",
                        description="由用户明确指定的路线锚点。",
                    )
                )
                order += 1
        return stops

    def _match_label_to_stop(
        self,
        *,
        label: str,
        day: int,
        order: int,
        time_slot: str,
        live_data: TravelDataBundle,
        confirmed_constraints: ConfirmedConstraints,
    ) -> RouteStop:
        if time_slot == "dining":
            candidate = self._match_candidate(label, live_data.foods)
            if candidate is not None:
                return self._candidate_to_stop(
                    candidate=candidate,
                    day=day,
                    order=order,
                    kind="food",
                    time_slot="dining",
                    fallback_description=label,
                )

        candidate = self._match_candidate(label, live_data.pois)
        if candidate is not None:
            return self._candidate_to_stop(
                candidate=candidate,
                day=day,
                order=order,
                kind="poi",
                time_slot=time_slot,
                fallback_description=label,
            )

        return RouteStop(
            stop_id=f"manual-{day}-{order}",
            day=day,
            order=order,
            name=label,
            kind="food" if time_slot == "dining" else "poi",
            time_slot=time_slot,  # type: ignore[arg-type]
            description=(
                "从模型行程中提取的手工站点。"
                if confirmed_constraints.must_visit_pois
                else "从当前行程草案中提取的站点。"
            ),
        )

    def _build_leg(
        self,
        *,
        request: TripPlanningRequest,
        confirmed_constraints: ConfirmedConstraints,
        origin: RouteStop,
        destination: RouteStop,
    ) -> RouteLeg:
        preferred_modes = confirmed_constraints.transport_preferences or request.transport_preferences
        if origin.location and destination.location:
            try:
                live_leg = self.direction_client.estimate_leg(
                    origin=origin.location,
                    destination=destination.location,
                    city=request.city or request.destination,
                    transport_preferences=preferred_modes,
                )
                if live_leg is not None:
                    return RouteLeg(
                        leg_id=f"{origin.stop_id}-{destination.stop_id}",
                        day=origin.day,
                        from_stop_id=origin.stop_id,
                        from_stop_name=origin.name,
                        to_stop_id=destination.stop_id,
                        to_stop_name=destination.name,
                        recommended_mode=live_leg["mode"],
                        estimated_duration_minutes=live_leg["duration_minutes"],
                        estimated_distance_km=live_leg["distance_km"],
                        suggestion=live_leg["suggestion"],
                        source=live_leg["source"],
                        status="live",
                    )
            except (ProviderRequestError, ProviderUnavailableError, RuntimeError) as exc:
                logger.warning(
                    "Route leg degraded to heuristic: from=%s to=%s reason=%s transport_preferences=%s",
                    origin.name,
                    destination.name,
                    f"{type(exc).__name__}: {exc}",
                    preferred_modes,
                )
        return self._heuristic_leg(
            origin=origin,
            destination=destination,
            transport_preferences=preferred_modes,
        )

    def _heuristic_leg(
        self,
        *,
        origin: RouteStop,
        destination: RouteStop,
        transport_preferences: list[str],
    ) -> RouteLeg:
        same_district = (
            origin.district
            and destination.district
            and origin.district == destination.district
        )
        if "步行" in transport_preferences and same_district:
            mode = "步行"
            duration = 18
            distance = 1.4
        elif "打车" in transport_preferences:
            mode = "打车"
            duration = 22 if same_district else 35
            distance = 3.5 if same_district else 9.2
        else:
            mode = "地铁 + 步行"
            duration = 28 if same_district else 46
            distance = 2.6 if same_district else 11.5

        return RouteLeg(
            leg_id=f"{origin.stop_id}-{destination.stop_id}",
            day=origin.day,
            from_stop_id=origin.stop_id,
            from_stop_name=origin.name,
            to_stop_id=destination.stop_id,
            to_stop_name=destination.name,
            recommended_mode=mode,
            estimated_duration_minutes=duration,
            estimated_distance_km=distance,
            suggestion=f"从 {origin.name} 前往 {destination.name} 优先采用 {mode}，此结果为启发式估算。",
            source=SourceReference(
                provider="heuristic-route",
                label="启发式路段估算",
                fetched_at=datetime.now(timezone.utc),
                status="degraded",
                note="高德路径规划暂不可用，当前结果基于片区级启发式估算。",
            ),
            status="estimated",
        )

    def _build_alternatives(
        self,
        *,
        stops: list[RouteStop],
        live_data: TravelDataBundle,
        confirmed_constraints: ConfirmedConstraints,
    ) -> list[AlternativeRoute]:
        used_names = {stop.name for stop in stops}
        unused_pois = [
            poi.name for poi in live_data.pois if poi.name not in used_names
        ][:3]
        if not unused_pois and not confirmed_constraints.must_visit_pois:
            return []
        differences = []
        if confirmed_constraints.pace_preference == "relaxed":
            differences.append("减少跨区移动，压缩站点数量。")
        else:
            differences.append("替换一部分高峰景点，降低排队风险。")
        if unused_pois:
            differences.append(f"可替换为 {'、'.join(unused_pois)}。")
        return [
            AlternativeRoute(
                title="低折返替代路线",
                summary="优先保留同片区站点，降低换乘密度。",
                stop_names=unused_pois,
                differences=differences,
            )
        ]

    def _candidate_to_stop(
        self,
        *,
        candidate: POICandidate | FoodCandidate | HotelCandidate,
        day: int,
        order: int,
        kind: str,
        time_slot: str,
        fallback_description: str,
    ) -> RouteStop:
        district = getattr(candidate, "district", None)
        return RouteStop(
            stop_id=str(candidate.id),
            day=day,
            order=order,
            name=candidate.name,
            kind=kind,  # type: ignore[arg-type]
            time_slot=time_slot,  # type: ignore[arg-type]
            address=candidate.address,
            district=district,
            description=fallback_description,
            location=getattr(candidate, "location", None),
            source=candidate.source,
        )

    @staticmethod
    def _match_candidate(
        label: str,
        candidates: Iterable[POICandidate | FoodCandidate],
    ) -> POICandidate | FoodCandidate | None:
        normalized = label.strip().lower()
        for candidate in candidates:
            if candidate.name.lower() in normalized or normalized in candidate.name.lower():
                return candidate
        return None

    @staticmethod
    def _build_strategy_text(constraints: ConfirmedConstraints) -> str:
        mode = "、".join(constraints.transport_preferences) or "地铁 + 步行"
        pace = constraints.pace_preference or "balanced"
        return f"以 {mode} 为主，采用 {pace} 节奏组织路线。"

    def _enrich_itinerary(
        self,
        *,
        request: TripPlanningRequest,
        confirmed_constraints: ConfirmedConstraints,
        itinerary: list[DailyPlan],
        live_data: TravelDataBundle,
    ) -> list[DailyPlan]:
        day_map = {item.day: item for item in itinerary}
        poi_pool = self._build_poi_labels(live_data, confirmed_constraints)
        dining_pool = self._build_food_labels(live_data)
        if not poi_pool:
            poi_pool = self._build_default_poi_labels(request, confirmed_constraints)
        if not dining_pool:
            dining_pool = self._build_default_food_labels(request, confirmed_constraints)
        enriched: list[DailyPlan] = []

        for day in range(1, request.days + 1):
            base_plan = day_map.get(day) or DailyPlan(day=day, theme=f"第 {day} 天")
            morning = self._meaningful_entries(base_plan.morning)
            afternoon = self._meaningful_entries(base_plan.afternoon)
            evening = self._meaningful_entries(base_plan.evening)
            dining = self._meaningful_entries(base_plan.dining)

            if not morning:
                morning = self._pick_labels(poi_pool, start=(day - 1) * 2, count=1)
            if not afternoon:
                afternoon = self._pick_labels(
                    poi_pool,
                    start=((day - 1) * 2) + 1,
                    count=1,
                    exclude=set(morning),
                )
            if not evening:
                evening = self._pick_labels(
                    poi_pool,
                    start=((day - 1) * 2) + 2,
                    count=1,
                    exclude=set(morning + afternoon),
                )
            if not dining:
                dining = self._pick_labels(dining_pool, start=day - 1, count=1)

            theme = base_plan.theme.strip() if base_plan.theme else ""
            if not theme or theme.lower().startswith("day "):
                focus = " / ".join((morning + afternoon)[:2]) or request.destination
                theme = f"第 {day} 天 · {focus}"

            enriched.append(
                DailyPlan(
                    day=day,
                    theme=theme,
                    morning=morning,
                    afternoon=afternoon,
                    evening=evening,
                    dining=dining,
                )
            )

        return enriched

    @staticmethod
    def _build_poi_labels(
        live_data: TravelDataBundle,
        confirmed_constraints: ConfirmedConstraints,
    ) -> list[str]:
        labels: list[str] = []
        for phrase in confirmed_constraints.must_visit_pois:
            if phrase and phrase not in labels:
                labels.append(phrase)
        for poi in live_data.pois:
            label = poi.name
            if poi.district:
                label = f"{poi.name}（{poi.district}）"
            elif poi.address:
                label = f"{poi.name}（{poi.address}）"
            if label not in labels:
                labels.append(label)
        return labels

    @staticmethod
    def _build_food_labels(live_data: TravelDataBundle) -> list[str]:
        labels: list[str] = []
        for food in live_data.foods:
            detail = food.cuisine or food.address or "用餐"
            label = f"{food.name}（{detail}）"
            if label not in labels:
                labels.append(label)
        return labels

    @staticmethod
    def _build_default_poi_labels(
        request: TripPlanningRequest,
        confirmed_constraints: ConfirmedConstraints,
    ) -> list[str]:
        anchor = (
            confirmed_constraints.must_visit_pois[:2]
            or confirmed_constraints.interests[:2]
            or ["城市核心地标", "文化展览片区", "夜景步行区"]
        )
        labels = []
        for item in anchor:
            label = item if request.destination in item else f"{request.destination}{item}"
            if label not in labels:
                labels.append(label)
        if len(labels) < 3:
            for item in (
                f"{request.destination}历史街区",
                f"{request.destination}博物馆片区",
                f"{request.destination}夜景步行区",
            ):
                if item not in labels:
                    labels.append(item)
        return labels

    @staticmethod
    def _build_default_food_labels(
        request: TripPlanningRequest,
        confirmed_constraints: ConfirmedConstraints,
    ) -> list[str]:
        preferences = confirmed_constraints.food_preferences[:2] or ["本地特色餐", "口碑餐馆"]
        labels = []
        for item in preferences:
            label = item if request.destination in item else f"{request.destination}{item}"
            if label not in labels:
                labels.append(label)
        return labels

    @staticmethod
    def _meaningful_entries(entries: list[str]) -> list[str]:
        placeholders = {
            "待补充",
            "Flexible sightseeing",
            "Neighborhood walk",
            "Explore the destination core",
            "Flexible dining block",
            "Review live dining options on the day",
        }
        items = [item.strip() for item in entries if item and item.strip()]
        return [item for item in items if item not in placeholders]

    @staticmethod
    def _pick_labels(
        labels: list[str],
        *,
        start: int,
        count: int,
        exclude: set[str] | None = None,
    ) -> list[str]:
        if not labels:
            return []
        exclude = exclude or set()
        picks: list[str] = []
        size = len(labels)
        for offset in range(size):
            candidate = labels[(start + offset) % size]
            if candidate in exclude or candidate in picks:
                continue
            picks.append(candidate)
            if len(picks) >= count:
                break
        return picks

    @staticmethod
    def _limit_slot_labels(labels: list[str], time_slot: str) -> list[str]:
        meaningful = RouteDirectionsService._meaningful_entries(labels)
        if not meaningful:
            return []
        limit = 1 if time_slot == "dining" else 2
        return meaningful[:limit]
