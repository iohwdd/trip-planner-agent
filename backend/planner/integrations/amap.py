from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from planner.domain.schemas import POICandidate, SourceReference
from planner.integrations.base import BaseIntegrationClient


class AmapPOIClient(BaseIntegrationClient):
    def search_pois(
        self,
        *,
        destination: str,
        city: str | None,
        keywords: list[str],
    ) -> list[POICandidate]:
        fetched_at = datetime.now(timezone.utc)
        collected: list[POICandidate] = []
        seen: set[str] = set()
        for search_text in self._build_queries(destination, keywords):
            params = {
                "key": self.provider_config.api_key,
                "keywords": search_text,
                "region": city or destination,
                "show_fields": "business,photos,indoor,navi,children,business_area",
                "page_size": 8,
            }
            response = self._request_json(
                endpoint=self.provider_config.base_url or "",
                params=params,
                cache_key=self.build_cache_key("amap", params),
            )

            for index, item in enumerate(response.get("pois", [])):
                poi = self._normalize_poi(item, fetched_at, index)
                if poi is None:
                    continue
                dedupe_key = poi.id or f"{poi.name}|{poi.address or ''}"
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                collected.append(poi)
                if len(collected) >= 12:
                    return collected
        return collected

    @staticmethod
    def _build_queries(destination: str, keywords: list[str]) -> list[str]:
        destination = destination.strip()
        normalized_keywords = [item.strip() for item in keywords if item and item.strip()]
        fallback_terms = ["景点", "地标", "博物馆", "步行街", "公园"]

        ordered_queries: list[str] = []
        if normalized_keywords:
            ordered_queries.append(" ".join([destination, *normalized_keywords]))
        ordered_queries.extend(
            f"{destination} {term}".strip()
            for term in [*normalized_keywords, *fallback_terms]
        )
        ordered_queries.append(destination)

        deduped: list[str] = []
        seen: set[str] = set()
        for query in ordered_queries:
            if query and query not in seen:
                seen.add(query)
                deduped.append(query)
        return deduped

    @staticmethod
    def _normalize_poi(
        item: dict[str, Any], fetched_at: datetime, index: int
    ) -> POICandidate | None:
        name = item.get("name")
        if not name:
            return None
        business = item.get("business") if isinstance(item.get("business"), dict) else {}
        rating = business.get("rating") or item.get("rating")
        try:
            normalized_rating = float(rating) if rating is not None else None
        except (TypeError, ValueError):
            normalized_rating = None

        return POICandidate(
            id=str(item.get("id") or item.get("name") or index),
            name=str(name),
            city=item.get("cityname"),
            district=item.get("adname"),
            address=item.get("address"),
            category=item.get("type"),
            location=item.get("location"),
            rating=normalized_rating,
            source=SourceReference(
                provider="amap",
                label="高德 POI 检索",
                fetched_at=fetched_at,
                url=None,
                status="live",
            ),
        )


class AmapDirectionClient(BaseIntegrationClient):
    WALKING_ENDPOINT = "https://restapi.amap.com/v5/direction/walking"
    TRANSIT_ENDPOINT = "https://restapi.amap.com/v5/direction/transit/integrated"
    LEGACY_TRANSIT_ENDPOINT = "https://restapi.amap.com/v3/direction/transit/integrated"
    DRIVING_ENDPOINT = "https://restapi.amap.com/v5/direction/driving"

    def estimate_leg(
        self,
        *,
        origin: str,
        destination: str,
        city: str | None,
        transport_preferences: list[str],
    ) -> dict[str, Any] | None:
        modes = self._ordered_modes(transport_preferences)
        for mode in modes:
            params = {
                "key": self.provider_config.api_key,
                "origin": origin,
                "destination": destination,
            }
            endpoint = self.TRANSIT_ENDPOINT
            if mode == "walking":
                endpoint = self.WALKING_ENDPOINT
                params["show_fields"] = "cost"
                params["alternative_route"] = 1
            elif mode == "driving":
                endpoint = self.DRIVING_ENDPOINT
                params["show_fields"] = "cost"
                params["strategy"] = 32
            else:
                transit_city_code = self._normalize_transit_city_code(city)
                if transit_city_code:
                    params["city1"] = transit_city_code
                    params["city2"] = transit_city_code
                    params["strategy"] = 0
                    params["show_fields"] = "cost"
                    params["AlternativeRoute"] = 1
                else:
                    endpoint = self.LEGACY_TRANSIT_ENDPOINT
                    params["city"] = city or ""
                    params["cityd"] = city or ""
                    params["strategy"] = 0

            response = self._request_json(
                endpoint=endpoint,
                params=params,
                cache_key=self.build_cache_key(f"amap-direction-{mode}", params),
            )
            normalized = self._normalize_direction_response(mode, response)
            if normalized is not None:
                return normalized
        return None

    @staticmethod
    def _ordered_modes(transport_preferences: list[str]) -> list[str]:
        if any(item in {"步行"} for item in transport_preferences):
            return ["walking", "transit"]
        if any(item in {"打车", "自驾"} for item in transport_preferences):
            return ["driving", "transit"]
        return ["transit", "walking"]

    @staticmethod
    def _normalize_direction_response(
        mode: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if str(payload.get("status")) not in {"1", ""}:
            return None
        route = payload.get("route")
        if not isinstance(route, dict):
            return None

        duration_seconds = None
        distance_meters = None
        suggestion = None
        mode_label = {
            "walking": "步行",
            "driving": "打车 / 自驾",
            "transit": "地铁 / 公交",
        }[mode]

        if mode == "transit":
            transits = route.get("transits")
            if not isinstance(transits, list) or not transits:
                return None
            best = transits[0]
            duration_seconds = AmapDirectionClient._extract_duration_seconds(best)
            distance_meters = AmapDirectionClient._safe_int(best.get("distance"))
            segments = best.get("segments")
            if isinstance(segments, list) and segments:
                suggestion = "优先公共交通，减少核心区停车和拥堵。"
        else:
            paths = route.get("paths")
            if not isinstance(paths, list) or not paths:
                return None
            best = paths[0]
            duration_seconds = AmapDirectionClient._extract_duration_seconds(best)
            distance_meters = AmapDirectionClient._safe_int(best.get("distance"))
            suggestion = (
                "适合步行串联相邻站点。"
                if mode == "walking"
                else "适合跨区转场或夜间回程。"
            )

        if duration_seconds is None:
            return None

        fetched_at = datetime.now(timezone.utc)
        return {
            "mode": mode_label,
            "duration_minutes": max(1, round(duration_seconds / 60)),
            "distance_km": round((distance_meters or 0) / 1000, 1)
            if distance_meters is not None
            else None,
            "suggestion": suggestion or "优先使用地图返回的推荐路线。",
            "source": SourceReference(
                provider="amap",
                label="高德路径规划",
                fetched_at=fetched_at,
                status="live",
            ),
        }

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_duration_seconds(payload: dict[str, Any]) -> int | None:
        cost = payload.get("cost")
        if isinstance(cost, dict):
            duration = AmapDirectionClient._safe_int(cost.get("duration"))
            if duration is not None:
                return duration
        return AmapDirectionClient._safe_int(payload.get("duration"))

    @staticmethod
    def _normalize_transit_city_code(city: str | None) -> str | None:
        normalized = (city or "").strip()
        if normalized.isdigit():
            return normalized
        return None
