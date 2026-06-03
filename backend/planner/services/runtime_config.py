from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str | None
    api_key: str | None
    timeout_seconds: float
    max_retries: int


@dataclass(frozen=True)
class QwenConfig:
    api_key: str | None
    base_url: str
    model: str
    timeout_seconds: float
    temperature: float
    enable_thinking: bool


@dataclass(frozen=True)
class RedisConfig:
    host: str | None = None
    port: int = 6379
    password: str | None = None
    database: int = 0

    @property
    def enabled(self) -> bool:
        return bool(self.host)


@dataclass(frozen=True)
class MinioConfig:
    endpoint: str | None = None
    port: int = 9000
    secure: bool = False
    access_key: str | None = None
    secret_key: str | None = None
    bucket: str = "trip-assistant"


@dataclass(frozen=True)
class KnowledgeBaseConfig:
    persist_directory: str
    collection_prefix: str
    embedding_model: str
    reranker_model: str
    chunk_size: int
    chunk_overlap: int
    retrieval_k: int
    rerank_top_n: int


@dataclass(frozen=True)
class RuntimeConfig:
    default_city: str | None
    cache_ttl_seconds: int
    rate_limit_seconds: float
    qwen: QwenConfig
    amap: ProviderConfig
    baidu: ProviderConfig
    redis: RedisConfig = field(default_factory=RedisConfig)
    minio: MinioConfig = field(default_factory=MinioConfig)
    knowledge: KnowledgeBaseConfig | None = None


def _float_env(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _int_env(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_runtime_config() -> RuntimeConfig:
    timeout = _float_env("TRIP_PLANNER_REQUEST_TIMEOUT_SECONDS", 60.0)
    retries = _int_env("TRIP_PLANNER_MAX_RETRIES", 2)

    return RuntimeConfig(
        default_city=os.getenv("TRIP_PLANNER_DEFAULT_CITY") or None,
        cache_ttl_seconds=_int_env("TRIP_PLANNER_CACHE_TTL_SECONDS", 300),
        rate_limit_seconds=_float_env("TRIP_PLANNER_RATE_LIMIT_SECONDS", 0.2),
        qwen=QwenConfig(
            api_key=os.getenv("DASHSCOPE_API_KEY") or None,
            base_url=os.getenv(
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            model=os.getenv("QWEN_MODEL", "qwen3.5-plus"),
            timeout_seconds=timeout,
            temperature=_float_env("QWEN_TEMPERATURE", 0.3),
            enable_thinking=_bool_env("QWEN_ENABLE_THINKING", False),
        ),
        amap=ProviderConfig(
            name="amap",
            base_url=os.getenv("AMAP_TEXT_SEARCH_URL")
            or "https://restapi.amap.com/v5/place/text",
            api_key=os.getenv("AMAP_API_KEY") or None,
            timeout_seconds=timeout,
            max_retries=retries,
        ),
        baidu=ProviderConfig(
            name="baidu",
            base_url=os.getenv("BAIDU_PLACE_SEARCH_URL")
            or "https://api.map.baidu.com/place/v2/search",
            api_key=os.getenv("BAIDU_MAPS_API_KEY") or None,
            timeout_seconds=timeout,
            max_retries=retries,
        ),
        redis=RedisConfig(
            host=(os.getenv("REDIS_HOST", "localhost") or None),
            port=_int_env("REDIS_PORT", 6379),
            password=os.getenv("REDIS_PASSWORD") or None,
            database=_int_env("REDIS_DATABASE", 0),
        ),
        minio=MinioConfig(
            endpoint=os.getenv("MINIO_ENDPOINT") or None,
            port=_int_env("MINIO_PORT", 9000),
            secure=_bool_env("MINIO_SECURE", False),
            access_key=os.getenv("MINIO_AK") or None,
            secret_key=os.getenv("MINIO_SK") or None,
            bucket=os.getenv("MINIO_BUCKET", "trip-assistant"),
        ),
        knowledge=KnowledgeBaseConfig(
            persist_directory=os.getenv(
                "KNOWLEDGE_CHROMA_DIR",
                os.path.join(os.getcwd(), ".data", "chroma"),
            ),
            collection_prefix=os.getenv("KNOWLEDGE_COLLECTION_PREFIX", "knowledge"),
            embedding_model=os.getenv(
                "KNOWLEDGE_EMBEDDING_MODEL",
                "shibing624/text2vec-base-chinese",
            ),
            reranker_model=os.getenv(
                "KNOWLEDGE_RERANKER_MODEL",
                "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
            ),
            chunk_size=_int_env("KNOWLEDGE_CHUNK_SIZE", 600),
            chunk_overlap=_int_env("KNOWLEDGE_CHUNK_OVERLAP", 100),
            retrieval_k=_int_env("KNOWLEDGE_RETRIEVAL_K", 12),
            rerank_top_n=_int_env("KNOWLEDGE_RERANK_TOP_N", 4),
        ),
    )
