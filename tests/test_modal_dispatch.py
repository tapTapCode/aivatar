from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from src.dispatch.modal import ModalJobDispatcher, callback_payload, sign_payload, verify_signature
from src.queue.base import JobMessage
from src.schemas.scene import ProjectScript


def test_modal_signature_is_verified_without_leaking_payload() -> None:
    body = b'{"job":"test"}'
    signature = sign_payload(body, secret="test-secret")
    assert verify_signature(body, signature, secret="test-secret")
    assert not verify_signature(body, signature, secret="other-secret")
    assert signature == hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()


def test_completed_callback_carries_only_explicit_output_metadata() -> None:
    payload = json.loads(
        callback_payload(
            state="COMPLETED",
            stage="complete",
            output={"asset_id": "video_test", "uri": "s3://private/video.mp4"},
        )
    )
    assert payload["state"] == "COMPLETED"
    assert payload["output"]["asset_id"] == "video_test"


@pytest.mark.asyncio
async def test_modal_dispatch_posts_signed_self_contained_payload() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        captured["signature"] = request.headers["X-Aivatar-Signature"]
        return httpx.Response(202)

    project = ProjectScript.model_validate(
        {
            "project_id": "modal-test",
            "schema_version": "1.0",
            "output": {"width": 640, "height": 360},
            "scenes": [
                {
                    "scene_id": "presenter",
                    "order": 1,
                    "visual_format": "PRESENTER",
                    "narration_text": "A short authorized test.",
                    "avatar_id": "avatar_approved",
                    "voice_id": "voice_approved",
                }
            ],
        }
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    dispatcher = ModalJobDispatcher(
        endpoint_url="https://modal.example/enqueue",
        dispatch_secret="test-secret",
        callback_url="https://aivatar.example/v1/internal/modal-jobs/{job_id}",
        client=client,
    )
    job = JobMessage(
        job_id="job_test", video_id="vid_test", project_id="modal-test", owner_id="owner"
    )
    await dispatcher.submit(job=job, project=project)
    await client.aclose()

    body = captured["body"]
    assert isinstance(body, bytes)
    assert verify_signature(body, str(captured["signature"]), secret="test-secret")
    payload = json.loads(body)
    assert payload["callback_url"].endswith("/job_test")
    assert payload["project"]["project_id"] == "modal-test"
