from __future__ import annotations

from pathlib import Path

class StorageUnavailable(RuntimeError):
    pass


class R2Storage:
    """Cloudflare R2 storage through its S3-compatible API."""

    def __init__(self, account_id: str | None, access_key_id: str | None, secret_access_key: str | None, bucket: str) -> None:
        self.account_id = account_id
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.bucket = bucket

    @property
    def configured(self) -> bool:
        return bool(self.account_id and self.access_key_id and self.secret_access_key and self.bucket)

    def _client(self):
        if not self.configured:
            raise StorageUnavailable("Cloudflare R2 credentials are not configured")
        import boto3

        return boto3.client(
            service_name="s3",
            endpoint_url=f"https://{self.account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name="auto",
        )

    @staticmethod
    def project_key(project_id: str, category: str, filename: str) -> str:
        return f"projects/{project_id}/{category.strip('/')}/{filename}"

    def upload_file(self, source: Path, key: str, content_type: str | None = None) -> dict:
        if not source.exists():
            raise FileNotFoundError(source)
        extra = {"ContentType": content_type} if content_type else None
        client = self._client()
        if extra:
            client.upload_file(str(source), self.bucket, key, ExtraArgs=extra)
        else:
            client.upload_file(str(source), self.bucket, key)
        head = client.head_object(Bucket=self.bucket, Key=key)
        return {"bucket": self.bucket, "key": key, "etag": str(head.get("ETag", "")).strip('"'), "size": int(head.get("ContentLength", 0))}

    def download_file(self, key: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._client().download_file(self.bucket, key, str(destination))
        return destination

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError
        try:
            self._client().head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404:
                return False
            raise
