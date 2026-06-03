from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from planner.domain.schemas import FoodCandidate, HotelCandidate, SourceReference
from planner.integrations.base import BaseIntegrationClient


class BaiduPlaceClient(BaseIntegrationClient):
    def search_foods(
        self,
        *,
        destination: str,
        city: str | None,
        keywords: list[str],
    ) -> list[FoodCandidate]:
        fetched_at = datetime.now(timezone.utc)
        places = self._search_food_places(
            destination=destination,
            region=city or destination,
            keywords=keywords,
        )
        results: list[FoodCandidate] = []
        for index, item in enumerate(places):
            detail = item.get("detail_info", {})
            cuisine = detail.get("tag") or item.get("tag")
            results.append(
                FoodCandidate(
                    id=str(item.get("uid") or index),
                    name=item.get("name", "未知餐厅"),
                    city=item.get("city") or city or destination,
                    address=item.get("address"),
                    location=self._normalize_location(item.get("location")),
                    cuisine=(cuisine.split(";")[0] if isinstance(cuisine, str) else None),
                    average_cost=self._to_float(detail.get("price") or item.get("price")),
                    rating=self._to_float(
                        detail.get("overall_rating") or item.get("overall_rating")
                    ),
                    source=SourceReference(
                        provider="baidu",
                        label="百度本地生活检索",
                        fetched_at=fetched_at,
                        status="live",
                    ),
                )
            )
        return results

    def search_hotels(
        self,
        *,
        destination: str,
        city: str | None,
        budget: float | None,
        days: int,
        preferences: list[str],
    ) -> list[HotelCandidate]:
        _ = budget, days
        region = city or destination
        places = self._search_hotel_places(
            destination=destination,
            region=region,
            preferences=preferences,
        )
        fetched_at = datetime.now(timezone.utc)
        results: list[HotelCandidate] = []
        for index, item in enumerate(places):
            detail = item.get("detail_info", {})
            price = self._to_float(detail.get("price") or item.get("price"))
            results.append(
                HotelCandidate(
                    id=str(item.get("uid") or index),
                    name=item.get("name", "未知酒店"),
                    city=item.get("city") or region,
                    address=item.get("address"),
                    location=self._normalize_location(item.get("location")),
                    price_min=price,
                    price_max=price,
                    rating=self._to_float(
                        detail.get("overall_rating") or item.get("overall_rating")
                    ),
                    source=SourceReference(
                        provider="baidu",
                        label="百度酒店候选检索",
                        fetched_at=fetched_at,
                        status="live",
                        note=(
                            "当前住宿候选来自地图地点检索，房态和价格需人工确认，预算适配为下游估算。"
                        ),
                    ),
                )
            )
        return results

    def _search_places(
        self,
        *,
        query: str,
        region: str,
        tag: str,
        cache_prefix: str,
    ) -> list[dict]:
        params = {
            "query": query,
            "region": region,
            "city_limit": "true",
            "tag": tag,
            "output": "json",
            "scope": 2,
            "page_size": 10,
            "ak": self.provider_config.api_key,
        }
        response = self._request_json(
            endpoint=self.provider_config.base_url or "",
            params=params,
            cache_key=self.build_cache_key(cache_prefix, params),
        )
        return response.get("results", [])

    def _search_food_places(
        self,
        *,
        destination: str,
        region: str,
        keywords: list[str],
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for query in self._build_food_queries(destination, keywords):
            for item in self._search_places(
                query=query,
                region=region,
                tag="美食",
                cache_prefix="baidu-food",
            ):
                dedupe_key = str(item.get("uid") or item.get("name") or "")
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                collected.append(item)
                if len(collected) >= 10:
                    return collected
        return collected

    def _search_hotel_places(
        self,
        *,
        destination: str,
        region: str,
        preferences: list[str],
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for query in self._build_hotel_queries(destination, preferences):
            for item in self._search_places(
                query=query,
                region=region,
                tag="酒店",
                cache_prefix="baidu-hotel",
            ):
                if not self._is_valid_hotel_place(item, region):
                    continue
                dedupe_key = str(item.get("uid") or item.get("name") or "")
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                collected.append(item)
                if len(collected) >= 10:
                    return collected
        return collected

    @staticmethod
    def _build_food_queries(destination: str, keywords: list[str]) -> list[str]:
        normalized_keywords = [item.strip() for item in keywords if item and item.strip()]
        fallback_queries = [
            "美食",
            "餐厅",
            "小吃",
            f"{destination} 美食".strip(),
            f"{destination} 小吃".strip(),
        ]

        ordered_queries: list[str] = []
        if normalized_keywords:
            ordered_queries.append(" ".join(normalized_keywords))
            ordered_queries.extend(normalized_keywords)
            ordered_queries.extend(
                f"{destination} {keyword}".strip() for keyword in normalized_keywords
            )
        ordered_queries.extend(fallback_queries)

        deduped: list[str] = []
        seen: set[str] = set()
        for query in ordered_queries:
            if query and query not in seen:
                seen.add(query)
                deduped.append(query)
        return deduped

    @staticmethod
    def _build_hotel_queries(destination: str, preferences: list[str]) -> list[str]:
        normalized_preferences = [
            item.strip() for item in preferences if item and item.strip()
        ]

        def with_hotel_suffix(text: str) -> str:
            if "酒店" in text or "住宿" in text:
                return text
            return f"{text} 酒店".strip()

        ordered_queries: list[str] = [
            f"{destination} 酒店".strip(),
            f"{destination} 地铁站 酒店".strip(),
            f"{destination} 市中心 酒店".strip(),
        ]

        if normalized_preferences:
            ordered_queries.extend(
                f"{destination} {with_hotel_suffix(preference)}".strip()
                for preference in normalized_preferences
            )
            ordered_queries.append(
                f"{destination} {' '.join(normalized_preferences)} 酒店".strip()
            )
            ordered_queries.extend(
                with_hotel_suffix(preference) for preference in normalized_preferences
            )

        deduped: list[str] = []
        seen: set[str] = set()
        for query in ordered_queries:
            if query and query not in seen:
                seen.add(query)
                deduped.append(query)
        return deduped

    @staticmethod
    def _is_valid_hotel_place(item: dict[str, Any], region: str) -> bool:
        if not isinstance(item, dict):
            return False
        if item.get("num") is not None:
            return False

        name = str(item.get("name") or "").strip()
        if not name or name.endswith(("市", "区", "县", "省")):
            return False

        detail = item.get("detail_info") if isinstance(item.get("detail_info"), dict) else {}
        detail_type = str(detail.get("type") or "").lower()
        tags = " ".join(
            str(value)
            for value in (
                detail.get("tag"),
                detail.get("classified_poi_tag"),
                item.get("tag"),
            )
            if value
        )
        if detail_type and detail_type != "hotel":
            return False
        if "酒店" not in tags and detail_type != "hotel":
            return False

        address = str(item.get("address") or "")
        city = str(item.get("city") or "")
        province = str(item.get("province") or "")
        area = str(item.get("area") or "")
        location_text = " ".join(part for part in (city, province, area, address) if part)
        if region and region not in location_text and f"{region}市" not in location_text:
            return False

        return bool(item.get("uid")) and bool(address or detail)

    @staticmethod
    def _to_float(value: object) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_location(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            lng = value.get("lng")
            lat = value.get("lat")
            if lng is None or lat is None:
                return None
            return f"{lng},{lat}"
        return None
