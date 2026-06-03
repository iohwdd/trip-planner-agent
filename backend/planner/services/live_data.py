from __future__ import annotations

import logging

from planner.domain.exceptions import ProviderRequestError, ProviderUnavailableError
from planner.domain.schemas import ProviderStatus, TravelDataBundle, TripPlanningRequest
from planner.integrations.amap import AmapPOIClient
from planner.integrations.baidu import BaiduPlaceClient
from planner.integrations.base import RateLimiter, build_cache_store
from planner.services.runtime_config import RuntimeConfig

logger = logging.getLogger(__name__)


class LiveDataService:
    def __init__(self, config: RuntimeConfig) -> None:
        cache = build_cache_store(config.cache_ttl_seconds, config.redis)
        limiter = RateLimiter(config.rate_limit_seconds)
        self.amap = AmapPOIClient(config.amap, cache, limiter)
        self.baidu = BaiduPlaceClient(config.baidu, cache, limiter)

    def fetch_all(self, request: TripPlanningRequest) -> TravelDataBundle:
        bundle = TravelDataBundle()
        city = request.city or request.destination

        bundle.pois, poi_status = self._safe_fetch(
            provider="amap",
            func=lambda: self.amap.search_pois(
                destination=request.destination,
                city=city,
                keywords=request.interests,
            ),
        )
        bundle.foods, food_status = self._safe_fetch(
            provider="baidu-food",
            func=lambda: self.baidu.search_foods(
                destination=request.destination,
                city=city,
                keywords=request.food_preferences,
            ),
        )
        bundle.hotels, hotel_status = self._safe_fetch(
            provider="baidu-hotel",
            func=lambda: self.baidu.search_hotels(
                destination=request.destination,
                city=city,
                budget=request.budget,
                days=request.days,
                preferences=request.hotel_preferences,
            ),
        )
        bundle.provider_statuses.extend([poi_status, food_status, hotel_status])
        return bundle

    @staticmethod
    def _safe_fetch(provider: str, func) -> tuple[list, ProviderStatus]:
        try:
            data = func()
            status = "success" if data else "degraded"
            message = "已获取实时数据" if data else "未返回可用记录"
            if status != "success":
                logger.warning(
                    "Live data provider degraded: provider=%s reason=%s records=%s",
                    provider,
                    message,
                    len(data),
                )
            return data, ProviderStatus(provider=provider, status=status, message=message)
        except ProviderUnavailableError as exc:
            logger.warning(
                "Live data provider unavailable: provider=%s reason=%s",
                provider,
                str(exc),
            )
            return [], ProviderStatus(
                provider=provider,
                status="degraded",
                message=str(exc),
            )
        except ProviderRequestError as exc:
            logger.warning(
                "Live data provider request failed: provider=%s reason=%s",
                provider,
                str(exc),
            )
            return [], ProviderStatus(
                provider=provider,
                status="failed",
                message=str(exc),
            )
