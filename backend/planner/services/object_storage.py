from __future__ import annotations

from io import BytesIO
from urllib.parse import urlparse

try:
    from minio import Minio
except ImportError:  # pragma: no cover - optional until dependency install
    Minio = None

from planner.services.runtime_config import MinioConfig


class MinioObjectStorage:
    def __init__(self, config: MinioConfig) -> None:
        self.config = config
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(
            self.config.endpoint
            and self.config.access_key
            and self.config.secret_key
            and self.config.bucket
            and Minio is not None
        )

    def upload_bytes(self, *, object_key: str, data: bytes, content_type: str) -> None:
        client = self._get_client()
        bucket = self.config.bucket
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.put_object(
            bucket,
            object_key,
            data=BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    def download_bytes(self, *, object_key: str) -> bytes:
        client = self._get_client()
        response = client.get_object(self.config.bucket, object_key)
        try:
            return response.read()
        finally:  # pragma: no branch - cleanup regardless of response type
            response.close()
            response.release_conn()

    def delete_object(self, *, object_key: str) -> None:
        client = self._get_client()
        try:
            client.remove_object(self.config.bucket, object_key)
        except Exception:
            return

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.enabled:
            raise RuntimeError("MinIO object storage is not configured")
        endpoint = self._normalized_endpoint()
        self._client = Minio(
            endpoint,
            access_key=self.config.access_key,
            secret_key=self.config.secret_key,
            secure=self.config.secure,
        )
        return self._client

    def _normalized_endpoint(self) -> str:
        endpoint = self.config.endpoint.strip()
        if "://" in endpoint:
            parsed = urlparse(endpoint)
            host = parsed.netloc or parsed.path
        else:
            host = endpoint
        if ":" in host:
            return host
        if self.config.port:
            return f"{host}:{self.config.port}"
        return host
