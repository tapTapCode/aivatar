from pipeline.gpu.runpod import RunPodServerlessClient


class Response:
    def __init__(self, payload):
        self.payload = payload
    def raise_for_status(self):
        return None
    def json(self):
        return self.payload


class FakeClient:
    calls = []
    def __init__(self, *args, **kwargs):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def request(self, method, url, headers=None, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/run"):
            return Response({"id": "job-1", "status": "IN_QUEUE"})
        if "/status/job-1" in url:
            return Response({"id": "job-1", "status": "COMPLETED", "output": {"r2_key": "x"}, "executionTime": 1250})
        return Response({"status": "CANCELLED"})


def test_runpod_async_contract(monkeypatch):
    import pipeline.gpu.runpod as module
    monkeypatch.setattr(module.httpx, "Client", FakeClient)
    client = RunPodServerlessClient("secret")
    result = client.run("endpoint", {"prompt": "test"}, timeout=1)
    assert result.job_id == "job-1"
    assert result.output["r2_key"] == "x"
    assert result.execution_ms == 1250
