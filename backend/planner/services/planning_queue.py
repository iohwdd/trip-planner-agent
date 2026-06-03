from __future__ import annotations

from collections import deque
from threading import Lock

try:
    import redis as redis_lib
except ImportError:  # pragma: no cover - optional until dependency install
    redis_lib = None

from planner.services.runtime_config import RedisConfig


class LocalPlanningQueue:
    def __init__(self) -> None:
        self._items: deque[str] = deque()
        self._lock = Lock()

    @property
    def available(self) -> bool:
        return False

    def enqueue(self, job_id: str) -> None:
        with self._lock:
            self._items.append(job_id)

    def pop_next(self) -> str | None:
        with self._lock:
            return self._items.popleft() if self._items else None


class RedisPlanningQueue:
    QUEUE_KEY = "planner:jobs:pending"

    def __init__(self, redis_config: RedisConfig) -> None:
        if redis_lib is None:
            raise RuntimeError("redis dependency is not installed")
        self._client = redis_lib.Redis(
            host=redis_config.host,
            port=redis_config.port,
            password=redis_config.password,
            db=redis_config.database,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        self._client.ping()

    @property
    def available(self) -> bool:
        return True

    def enqueue(self, job_id: str) -> None:
        self._client.rpush(self.QUEUE_KEY, job_id)

    def pop_next(self) -> str | None:
        return self._client.lpop(self.QUEUE_KEY)


def build_planning_queue(redis_config: RedisConfig):
    if redis_config.enabled:
        try:
            return RedisPlanningQueue(redis_config)
        except Exception:
            pass
    return LocalPlanningQueue()
