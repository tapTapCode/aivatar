from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from src.api.config import get_settings
from src.storage.s3 import S3RetentionStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload and verify a final MP4 in private R2")
    parser.add_argument("source", type=Path)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--video", required=True)
    return parser.parse_args()


async def upload() -> None:
    args = parse_args()
    settings = get_settings()
    store = S3RetentionStore(
        endpoint_url=settings.s3_endpoint_url,
        bucket=settings.s3_bucket,
        access_key_id=settings.s3_access_key,
        secret_access_key=settings.s3_secret_key,
        prefix=settings.final_video_r2_prefix,
    )
    uri = await store.put_file(
        args.source,
        key=f"{args.owner}/{args.project}/{args.video}/final.mp4",
    )
    print(f"Uploaded and checksum-verified: {uri}")


def run() -> None:
    asyncio.run(upload())


if __name__ == "__main__":
    run()
