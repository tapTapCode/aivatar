from __future__ import annotations

import argparse
import os

import uvicorn

from src.workers.service import create_worker_app


def run() -> None:
    parser = argparse.ArgumentParser(description="Run an isolated pipeline worker")
    parser.add_argument(
        "--kind",
        choices=("image", "video", "tts", "lipsync", "render"),
        default=os.environ.get("WORKER_KIND"),
        required=os.environ.get("WORKER_KIND") is None,
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = parser.parse_args()
    uvicorn.run(create_worker_app(args.kind), host=args.host, port=args.port)


if __name__ == "__main__":
    run()
