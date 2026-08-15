from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from src.providers.common import file_sha256


class S3RetentionStore:
    """Checksum-verifying S3-compatible mirror for retained provider artifacts."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        prefix: str = "retained/heygen",
        client: Any | None = None,
    ) -> None:
        if not all((endpoint_url, bucket, access_key_id, secret_access_key)):
            raise ValueError("complete S3/R2 configuration is required")
        if client is None:
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError("install the s3 extra to enable R2 retention") from exc
            client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name="auto",
            )
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")

    async def put_file(
        self, source: Path, *, key: str, metadata: dict[str, str] | None = None
    ) -> str:
        return await asyncio.to_thread(self._put_file, source, key, metadata)

    def object_key(self, key: str) -> str:
        """Return the normalized private object key without exposing credentials."""

        return "/".join(part for part in (self.prefix, key.strip("/")) if part)

    async def presigned_get_url(self, *, key: str, expires_seconds: int = 900) -> str:
        if not 1 <= expires_seconds <= 604_800:
            raise ValueError("presigned URL expiry must be between 1 second and 7 days")
        return await asyncio.to_thread(self._presigned_get_url, key, expires_seconds)

    async def presigned_get_uri(self, uri: str, *, expires_seconds: int = 900) -> str:
        expected_prefix = f"s3://{self.bucket}/"
        if not uri.startswith(expected_prefix):
            raise ValueError("retained object URI does not belong to the configured bucket")
        remote_key = uri.removeprefix(expected_prefix)
        if not 1 <= expires_seconds <= 604_800:
            raise ValueError("presigned URL expiry must be between 1 second and 7 days")
        return await asyncio.to_thread(
            self.client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.bucket, "Key": remote_key},
            ExpiresIn=expires_seconds,
        )

    def _presigned_get_url(self, key: str, expires_seconds: int) -> str:
        return str(
            self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": self.object_key(key)},
                ExpiresIn=expires_seconds,
            )
        )

    def _put_file(self, source: Path, key: str, metadata: dict[str, str] | None) -> str:
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        digest = file_sha256(source)
        object_metadata = {
            **(metadata or {}),
            "sha256": digest,
            "file_size_bytes": str(source.stat().st_size),
        }
        remote_key = self.object_key(key)
        self.client.upload_file(
            str(source),
            self.bucket,
            remote_key,
            ExtraArgs={
                "ContentType": "video/mp4",
                "Metadata": object_metadata,
            },
        )
        head_result = self.client.head_object(Bucket=self.bucket, Key=remote_key)
        if int(head_result.get("ContentLength", -1)) != source.stat().st_size:
            raise ValueError("R2 retained object size verification failed")
        remote_digest = (head_result.get("Metadata") or {}).get("sha256")
        if remote_digest != digest:
            raise ValueError("R2 retained object checksum metadata verification failed")
        remote_metadata = head_result.get("Metadata") or {}
        if remote_metadata.get("file_size_bytes") != str(source.stat().st_size):
            raise ValueError("R2 retained object size metadata verification failed")
        for key, value in object_metadata.items():
            if remote_metadata.get(key) != value:
                raise ValueError(f"R2 retained object metadata verification failed: {key}")
        return f"s3://{self.bucket}/{remote_key}"
