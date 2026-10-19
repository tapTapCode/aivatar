from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pipeline.models.entities import Channel, Project
from pipeline.production.locks import acquire_project_lock, release_project_lock
from pipeline.storage.db import Base


def test_project_lock_prevents_two_operators():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        channel = Channel(name="Lock Test")
        db.add(channel); db.commit(); db.refresh(channel)
        project = Project(channel_id=channel.id, name="P", script="script", expected_duration=60)
        db.add(project); db.commit(); db.refresh(project)
        acquire_project_lock(db, project, "operator-a", 300)
        try:
            acquire_project_lock(db, project, "operator-b", 300)
        except ValueError as exc:
            assert "operator-a" in str(exc)
        else:
            raise AssertionError("second operator unexpectedly acquired active lock")
        release_project_lock(db, project, "operator-a")
        acquire_project_lock(db, project, "operator-b", 300)
        assert project.lock_owner == "operator-b"
