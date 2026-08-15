from __future__ import annotations

from pathlib import Path

import pytest

from src.providers.common import file_sha256
from src.storage.s3 import S3RetentionStore


class FakeS3Client:
    def __init__(self) -> None:
        self.upload: tuple[str, str, str, dict] | None = None

    def upload_file(self, source: str, bucket: str, key: str, ExtraArgs: dict) -> None:
        self.upload = (source, bucket, key, ExtraArgs)

    def head_object(self, *, Bucket: str, Key: str) -> dict:
        assert self.upload is not None
        source, bucket, key, extra = self.upload
        assert (Bucket, Key) == (bucket, key)
        return {
            "ContentLength": Path(source).stat().st_size,
            "Metadata": extra["Metadata"],
        }

    def generate_presigned_url(
        self, operation: str, *, Params: dict, ExpiresIn: int
    ) -> str:
        assert operation == "get_object"
        return f"https://signed.example/{Params['Bucket']}/{Params['Key']}?ttl={ExpiresIn}"


@pytest.mark.asyncio
async def test_s3_retention_uploads_and_verifies_checksum_metadata(tmp_path: Path) -> None:
    source = tmp_path / "presenter.mp4"
    source.write_bytes(b"video")
    client = FakeS3Client()
    store = S3RetentionStore(
        endpoint_url="https://account.r2.cloudflarestorage.com",
        bucket="video-assets",
        access_key_id="access",
        secret_access_key="secret",
        prefix="retained/heygen",
        client=client,
    )
    uri = await store.put_file(
        source,
        key="project/job/video.mp4",
        metadata={"watermark_status": "PRESERVED"},
    )
    assert uri == "s3://video-assets/retained/heygen/project/job/video.mp4"
    assert client.upload is not None
    assert client.upload[3]["Metadata"]["sha256"] == file_sha256(source)
    assert client.upload[3]["Metadata"]["file_size_bytes"] == "5"
    assert client.upload[3]["Metadata"]["watermark_status"] == "PRESERVED"

    signed = await store.presigned_get_uri(uri, expires_seconds=300)
    assert signed == (
        "https://signed.example/video-assets/retained/heygen/project/job/video.mp4?ttl=300"
    )


@pytest.mark.asyncio
async def test_s3_retention_rejects_another_bucket_uri() -> None:
    store = S3RetentionStore(
        endpoint_url="https://account.r2.cloudflarestorage.com",
        bucket="video-assets",
        access_key_id="access",
        secret_access_key="secret",
        client=FakeS3Client(),
    )
    with pytest.raises(ValueError, match="configured bucket"):
        await store.presigned_get_uri("s3://another-bucket/private.mp4")
