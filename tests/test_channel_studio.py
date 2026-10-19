from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from pipeline.api.main import app
from pipeline.core.config import settings
from pipeline.models.entities import Channel, Avatar, Project, Job, Asset
from pipeline.storage.db import Base, get_db
from pipeline.studio.planning import ProductionOptions, build_plan
from pipeline.studio.production import run_production


@pytest.fixture
def studio(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings,"aivatar_workspace",tmp_path / "media")
    monkeypatch.setattr(settings,"aivatar_env","test")
    def get_test_db():
        with Session(engine, expire_on_commit=False) as db: yield db
    app.dependency_overrides[get_db] = get_test_db
    # Do not run global lifespan/recover real jobs in an isolated API test.
    client = TestClient(app)
    channel = client.post('/channels',json={"name":"Test channel"}).json()
    yield client, engine, channel
    app.dependency_overrides.clear()
    engine.dispose()


def test_script_preserved_and_distributed():
    text = ' '.join(f'word{i}' for i in range(600))
    options = ProductionOptions(channel_id='channel',name='Long video',script=text,mode='demo')
    plan = build_plan(options)
    assert ' '.join(s['narration'] for s in plan['scenes']) == text
    assert len(plan['scenes']) > 6
    assert plan['scenes'][0]['start'] == 0
    assert abs(plan['scenes'][-1]['end'] - 600/145*60) < .01
    assert any(s['type'] == 'PRESENTER' for s in plan['scenes'][-2:])
    assert all(a['end'] == b['start'] for a,b in zip(plan['scenes'],plan['scenes'][1:]))


def test_saved_voice_and_cross_channel_validation(studio):
    client, engine, channel = studio
    avatar = client.post('/avatars',json={'channel_id':channel['id'],'name':'Host','voice_id':'specific-voice'}).json()
    assert avatar['voice_id'] == 'specific-voice'
    other = client.post('/channels',json={'name':'Other channel'}).json()
    result = client.post('/studio/plan',json={'channel_id':other['id'],'avatar_id':avatar['id'],'name':'Video','script':'Test script','mode':'demo'})
    assert result.status_code == 422
    result = client.post('/projects',json={'channel_id':other['id'],'avatar_id':avatar['id'],'name':'Video','script':'Test script'})
    assert result.status_code == 422


def test_preflight_stops_unconfigured_paid_render(studio,monkeypatch):
    client, engine, channel = studio
    monkeypatch.setattr(settings,'ai33_api_key',None)
    monkeypatch.setattr(settings,'fal_api_key',None)
    options = {'channel_id':channel['id'],'name':'No paid request','script':'A visual story about forests.','presenter_target':0}
    review = client.post('/studio/plan',json=options).json()
    assert review['ready'] is False and len(review['blockers']) >= 2
    saved = client.post('/studio/productions',json=options).json()
    result = client.post(f"/studio/productions/{saved['project']['id']}/generate",json={'approved':True})
    assert result.status_code == 409
    with Session(engine) as db: assert db.scalars(select(Job)).first() is None


def test_duplicate_active_submission_reuses_job(studio):
    client,engine,channel = studio
    payload={'channel_id':channel['id'],'name':'Demo','script':'A short story.','mode':'demo'}
    saved=client.post('/studio/productions',json=payload).json()['project']
    with Session(engine) as db:
        job=Job(project_id=saved['id'],kind='studio_render',state='QUEUED');db.add(job);db.commit();job_id=job.id
    url=f"/studio/productions/{saved['id']}/generate"
    assert client.post(url,json={'approved':False}).status_code==422
    response=client.post(url,json={'approved':True}).json()
    assert response['job_id']==job_id and response['reused'] is True


def test_bad_media_rejected(studio):
    client,_,_=studio
    response=client.post('/studio/uploads/image',content=b'not an image',headers={'X-Filename':'image.png'})
    assert response.status_code==422
    response=client.post('/studio/uploads/image',content=b'x',headers={'X-Filename':'../bad.exe'})
    assert response.status_code==422


def test_demo_production_exports_video_captions_and_plan(studio):
    from pipeline.render.ffmpeg import run, ffprobe
    client,engine,channel=studio
    music=settings.aivatar_workspace / 'music.wav';music.parent.mkdir(parents=True,exist_ok=True)
    run(['ffmpeg','-y','-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=2',str(music)])
    options={'channel_id':channel['id'],'name':'Smoke test','script':'A short story about a beautiful forest and its wildlife.',
             'mode':'demo','presenter_target':0,'aspect_ratio':'9:16','resolution':'720p','music_path':str(music)}
    saved=client.post('/studio/productions',json=options).json()['project']
    stages=[]
    with Session(engine,expire_on_commit=False) as db:
        project=db.get(Project,saved['id'])
        result=run_production(db,project,lambda stage,fraction: stages.append(stage))
        assert project.state=='COMPLETED'
        assert project.actual_cost_usd==0
        assets=db.scalars(select(Asset).where(Asset.kind=='visual')).all()
        assert all(a.provider.startswith('mock') or a.provider.startswith('cache:mock') for a in assets)
    info=ffprobe(Path(result['final']))
    video=next(s for s in info['streams'] if s['codec_type']=='video')
    assert (video['width'],video['height'])==(720,1280)
    assert any(s['codec_type']=='audio' for s in info['streams'])
    assert 'Checking exported video' in stages
    for kind in ('video','captions','plan'):
        assert client.get(f"/studio/productions/{saved['id']}/files/{kind}").status_code==200
    assert client.get(f"/studio/productions/{saved['id']}/files/secrets").status_code==404


def test_demo_presenter_split_and_resumption(studio):
    client,engine,channel=studio
    options={'channel_id':channel['id'],'name':'Presenter test','script':' '.join(['A clear documentary narration about wildlife and nature.']*5),
             'mode':'demo','presenter_target':1,'aspect_ratio':'1:1','resolution':'720p','words_per_minute':220,'scene_seconds':5}
    saved=client.post('/studio/productions',json=options).json()['project']
    with Session(engine,expire_on_commit=False) as db:
        project=db.get(Project,saved['id'])
        def interrupt(stage,fraction):
            if stage.startswith('Producing scene 2/'):
                raise RuntimeError('Simulated interruption')
        with pytest.raises(RuntimeError,match='Simulated interruption'):
            run_production(db,project,interrupt)
        master_before=db.scalars(select(Asset).where(Asset.kind=='master_audio')).first().id
        presenter_before=db.scalars(select(Asset).where(Asset.kind=='presenter_clip')).first().id
        run_production(db,project)
        assert project.state=='COMPLETED'
        assert db.get(Asset,master_before)
        assert db.get(Asset,presenter_before)
        assert any(s.type=='SPLIT' for s in project.scenes)


def test_commercial_controls_are_safe_in_local_mode(studio):
    client, _, _ = studio
    status = client.get('/studio/commercial/status')
    assert status.status_code == 200
    body = status.json()
    assert body['credits'] >= 0
    assert body['features']['voice_preview'] is True
    assert body['features']['team_roles'] is False
    assert body['features']['stripe_subscriptions'] is False
    direction = client.post('/studio/commercial/scene-direction', json={
        'script': 'Open with the problem, show the process, and close with a useful next step.',
        'visual_style': 'clean documentary',
    })
    assert direction.status_code == 200
    assert direction.json()['scenes'][0]['direction'].startswith('presenter close-up')
    assert client.get('/studio/commercial/music/recommend').json()['selected'] is None

