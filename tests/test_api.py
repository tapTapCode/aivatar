from fastapi.testclient import TestClient
from pipeline.api.main import app
from uuid import uuid4

def test_health():
    with TestClient(app) as client:
        r=client.get("/health")
        assert r.status_code==200 and r.json()["ok"] is True

def test_provider_boundary():
    with TestClient(app) as client:
        data=client.get("/providers").json()
        assert any(x["id"]=="authorized_heygen" for x in data["presenter"])
        assert any(x["id"]=="flux_klein" for x in data["images"])

def test_generate_mock_voice_and_timestamps():
    with TestClient(app) as client:
        channel=client.post('/channels',json={'name':f'Voice Channel Phase2 {uuid4()}'}).json()
        project=client.post('/projects',json={'channel_id':channel['id'],'name':'Voice','script':'This is a real alignment test sentence. It has captions too.','expected_duration':3}).json()
        response=client.post(f"/projects/{project['id']}/voice",json={'provider':'mock_voice'})
        assert response.status_code==200
        data=response.json()
        assert data['timestamp_source']=='heuristic_fallback'
        assert data['word_count']>0
        detail=client.get(f"/projects/{project['id']}").json()
        assert detail['state']=='VOICE_READY'
