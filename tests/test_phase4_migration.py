from sqlalchemy import create_engine, inspect

from pipeline.models import entities  # noqa: F401
from pipeline.storage.db import Base


def test_phase4_schema_contains_budget_strategy_and_cache_tables():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    assert "asset_cache" in inspector.get_table_names()
    project_columns = {c["name"] for c in inspector.get_columns("projects")}
    scene_columns = {c["name"] for c in inspector.get_columns("scenes")}
    asset_columns = {c["name"] for c in inspector.get_columns("assets")}
    assert {"budget_usd", "visual_density"} <= project_columns
    assert {"asset_strategy", "motion_score", "estimated_visual_cost_usd", "graphic_template"} <= scene_columns
    assert "cache_key" in asset_columns
