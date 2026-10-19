from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from pipeline.providers.base import ProviderUnavailable


@dataclass(slots=True)
class RunPodJobResult:
    job_id: str
    status: str
    output: dict[str, Any]
    execution_ms: float | None = None
    delay_ms: float | None = None


class RunPodServerlessClient:
    """Minimal client for RunPod queue-based Serverless endpoints.

    Uses the documented /run, /status/{id}, /cancel/{id}, /retry/{id}, and /health operations.
    """

    def __init__(self, api_key: str | None, base_url: str = "https://api.runpod.ai/v2", timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderUnavailable("RUNPOD_API_KEY is not configured")
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _request(self, method: str, url: str, **kwargs) -> dict:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, url, headers=self._headers(), **kwargs)
            response.raise_for_status()
            return response.json()

    def submit(self, endpoint_id: str, payload: dict) -> str:
        data = self._request("POST", f"{self.base_url}/{endpoint_id}/run", json={"input": payload})
        job_id = data.get("id")
        if not job_id:
            raise RuntimeError(f"RunPod did not return a job id: {data}")
        return str(job_id)

    def status(self, endpoint_id: str, job_id: str) -> dict:
        return self._request("GET", f"{self.base_url}/{endpoint_id}/status/{job_id}")

    def wait(self, endpoint_id: str, job_id: str, timeout: float = 1800.0, poll_interval: float = 2.0) -> RunPodJobResult:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = self.status(endpoint_id, job_id)
            status = str(data.get("status", "UNKNOWN"))
            if status == "COMPLETED":
                return RunPodJobResult(
                    job_id=job_id,
                    status=status,
                    output=data.get("output") or {},
                    execution_ms=float(data["executionTime"]) if data.get("executionTime") is not None else None,
                    delay_ms=float(data["delayTime"]) if data.get("delayTime") is not None else None,
                )
            if status in {"FAILED", "CANCELLED", "TIMED_OUT"}:
                raise RuntimeError(f"RunPod job {job_id} ended as {status}: {data.get('error') or data}")
            time.sleep(poll_interval)
        self.cancel(endpoint_id, job_id)
        raise TimeoutError(f"RunPod job {job_id} exceeded {timeout:.0f}s")

    def run(self, endpoint_id: str, payload: dict, timeout: float = 1800.0) -> RunPodJobResult:
        return self.wait(endpoint_id, self.submit(endpoint_id, payload), timeout=timeout)

    def cancel(self, endpoint_id: str, job_id: str) -> dict:
        return self._request("POST", f"{self.base_url}/{endpoint_id}/cancel/{job_id}")

    def retry(self, endpoint_id: str, job_id: str) -> dict:
        return self._request("POST", f"{self.base_url}/{endpoint_id}/retry/{job_id}")

    def health(self, endpoint_id: str) -> dict:
        return self._request("GET", f"{self.base_url}/{endpoint_id}/health")
