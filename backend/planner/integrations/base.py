from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

import requests

try:
    import redis as redis_lib
except ImportError:  # pragma: no cover - optional until dependency install
    redis_lib = None

from planner.domain.exceptions import ProviderRequestError, ProviderUnavailableError
from planner.services.runtime_config import ProviderConfig, RedisConfig


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class CacheStore(Protocol):
    def get(self, key: str) -> Any | None: ...

    def set(self, key: str, value: Any) -> None: ...


class TTLCacheStore:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            if item.expires_at < time.monotonic():
                self._store.pop(key, None)
                return None
            return item.value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = CacheEntry(
                value=value,
                expires_at=time.monotonic() + self.ttl_seconds,
            )


class RedisCacheStore:
    def __init__(self, redis_config: RedisConfig, ttl_seconds: int) -> None:
        if redis_lib is None:
            raise RuntimeError("redis dependency is not installed")
        self.ttl_seconds = ttl_seconds
        self._client = redis_lib.Redis(
            host=redis_config.host,
            port=redis_config.port,
            password=redis_config.password,
            db=redis_config.database,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )

    def get(self, key: str) -> Any | None:
        try:
            value = self._client.get(key)
        except Exception:
            return None
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    def set(self, key: str, value: Any) -> None:
        try:
            payload = json.dumps(value, ensure_ascii=False)
            self._client.setex(key, self.ttl_seconds, payload)
        except Exception:
            return


def build_cache_store(ttl_seconds: int, redis_config: RedisConfig | None = None) -> CacheStore:
    if redis_config is not None and redis_config.enabled:
        try:
            return RedisCacheStore(redis_config, ttl_seconds)
        except Exception:
            pass
    return TTLCacheStore(ttl_seconds)


class RateLimiter:
    def __init__(self, min_interval_seconds: float) -> None:
        self.min_interval_seconds = min_interval_seconds
        self._lock = threading.Lock()
        self._last_called = 0.0

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_called
            if elapsed < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - elapsed)
            self._last_called = time.monotonic()


class BaseIntegrationClient:
    def __init__(
        self,
        provider_config: ProviderConfig,
        cache_store: CacheStore,
        rate_limiter: RateLimiter,
    ) -> None:
        self.provider_config = provider_config
        self.cache_store = cache_store
        self.rate_limiter = rate_limiter

    def _assert_configured(self) -> None:
        if not self.provider_config.base_url or not self.provider_config.api_key:
            raise ProviderUnavailableError(
                f"{self.provider_config.name} provider is not configured"
            )

    def _request_json(
        self,
        *,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        cache_key: str | None = None,
    ) -> dict[str, Any]:
        self._assert_configured()

        if cache_key:
            cached = self.cache_store.get(cache_key)
            if cached is not None:
                return cached

        attempt = 0
        last_error: Exception | None = None
        while attempt <= self.provider_config.max_retries:
            attempt += 1
            try:
                self.rate_limiter.wait()
                response = requests.request(
                    method=method,
                    url=endpoint,
                    params=params,
                    json=payload,
                    headers=headers,
                    timeout=self.provider_config.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                if cache_key:
                    self.cache_store.set(cache_key, data)
                return data
            except Exception as exc:
                last_error = exc
                if attempt > self.provider_config.max_retries:
                    break
                time.sleep(0.4 * attempt)

        raise ProviderRequestError(
            f"{self.provider_config.name} request failed: {last_error}"
        )

    @staticmethod
    def build_cache_key(prefix: str, params: dict[str, Any]) -> str:
        return f"{prefix}:{json.dumps(params, sort_keys=True, ensure_ascii=False)}"
