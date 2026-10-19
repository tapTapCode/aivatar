from pathlib import Path
import shutil

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pipeline.assets.service import generate_visual_assets, plan_visual_assets
from pipeline.core.config import settings
from pipeline.models.entities import Channel, Project, Scene
from pipeline.storage.db import Base


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg required")
def test_second_project_reuses_first_projects_visual_source(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "aivatar_workspace", tmp_path / "workspace")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        channel = Channel(name="Cache test")
        db.add(channel); db.commit(); db.refresh(channel)

        def make_project(name: str) -> Project:
            project = Project(
                channel_id=channel.id,
                name=name,
                script="test",
                state="PLANNING",
                expected_duration=2.0,
                budget_usd=5.0,
            )
            db.add(project); db.commit(); db.refresh(project)
            db.add(Scene(
                project_id=project.id,
                ordinal=1,
                start=0,
                end=2,
                type="FULL_VISUAL",
                visual_prompt="Archival portrait of a historic building at sunrise",
                motion="slow_push_in",
            ))
            db.commit(); db.refresh(project)
            return project

        first = make_project("first")
        plan_visual_assets(db, first)
        first_results = generate_visual_assets(db, first, mock=True)
        assert first_results[0]["cache_hit"] is False

        second = make_project("second")
        plan = plan_visual_assets(db, second)
        assert plan["cache_hits"] == [1]
        second_results = generate_visual_assets(db, second, mock=True)
        assert second_results[0]["cache_hit"] is True
        assert Path(second_results[0]["visual"]).exists()
