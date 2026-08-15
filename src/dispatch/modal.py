from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

import httpx

from src.queue.base import JobMessage
from src.schemas.scene import ProjectScript


def sign_payload(payload: bytes, *, secret: str) -> str:
    if not secret:
        raise ValueError("MODAL_DISPATCH_SECRET is required")
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_signature(payload: bytes, signature: str | None, *, secret: str) -> bool:
    if not signature or not secret:
        return False
    return hmac.compare_digest(sign_payload(payload, secret=secret), signature)


@dataclass(frozen=True)
class ModalJobDispatcher:
    """Submit a self-contained render request to the private Modal ingress."""

    endpoint_url: str
    dispatch_secret: str
    callback_url: str
    client: httpx.AsyncClient | None = None

    async def submit(self, *, job: JobMessage, project: ProjectScript) -> None:
        if not self.endpoint_url.startswith("https://"):
            raise ValueError("MODAL_DISPATCH_URL must use HTTPS")
        payload = {
            "job": job.model_dump(mode="json"),
            "project": project.model_dump(mode="json"),
            "callback_url": self.callback_url.format(job_id=job.job_id),
        }
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        headers = {
            "Content-Type": "application/json",
            "X-Aivatar-Signature": sign_payload(body, secret=self.dispatch_secret),
        }
        client = self.client or httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        close_client = self.client is None
        try:
            response = await client.post(self.endpoint_url, content=body, headers=headers)
            response.raise_for_status()
        finally:
            if close_client:
                await client.aclose()


def callback_payload(
    *, state: str, stage: str, output: dict[str, Any] | None = None, failed: bool = False
) -> bytes:
    payload: dict[str, Any] = {"state": state, "stage": stage}
    if output:
        payload["output"] = output
    if failed:
        payload["failed"] = True
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
