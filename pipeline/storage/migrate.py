from sqlalchemy import inspect, text

from pipeline.models import entities  # noqa: F401
from pipeline.storage.db import Base, engine

SCHEMA_VERSION = 6


def _add_column(conn, table: str, existing: set[str], name: str, ddl: str) -> None:
    if name not in existing:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        existing.add(name)


def migrate() -> None:
    # create_all makes fresh mock/dev databases immediately usable. Explicit ALTER statements keep
    # existing local SQLite projects forward-compatible when Alembic CLI is not installed.
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        if "scenes" in tables:
            columns = {column["name"] for column in inspector.get_columns("scenes")}
            _add_column(conn, "scenes", columns, "layout_json", "JSON")
            _add_column(conn, "scenes", columns, "asset_strategy", "VARCHAR(40) DEFAULT 'flux_motion'")
            _add_column(conn, "scenes", columns, "motion_score", "FLOAT DEFAULT 0")
            _add_column(conn, "scenes", columns, "estimated_visual_cost_usd", "FLOAT DEFAULT 0")
            _add_column(conn, "scenes", columns, "graphic_template", "VARCHAR(60)")
            conn.execute(text("UPDATE scenes SET layout_json = '{}' WHERE layout_json IS NULL"))
            conn.execute(text("UPDATE scenes SET asset_strategy = 'flux_motion' WHERE asset_strategy IS NULL"))
        if "projects" in tables:
            columns = {column["name"] for column in inspector.get_columns("projects")}
            _add_column(conn, "projects", columns, "budget_usd", "FLOAT DEFAULT 5.0")
            _add_column(conn, "projects", columns, "production_json", "JSON DEFAULT '{}' NOT NULL")
            _add_column(conn, "projects", columns, "visual_density", "FLOAT DEFAULT 0.65")
            _add_column(conn, "projects", columns, "lock_owner", "VARCHAR(160)")
            _add_column(conn, "projects", columns, "lock_expires_at", "DATETIME")
        if "jobs" in tables:
            columns = {column["name"] for column in inspector.get_columns("jobs")}
            _add_column(conn, "jobs", columns, "max_attempts", "INTEGER DEFAULT 3")
            _add_column(conn, "jobs", columns, "retryable", "BOOLEAN DEFAULT 1")
            _add_column(conn, "jobs", columns, "resume_count", "INTEGER DEFAULT 0")
            _add_column(conn, "jobs", columns, "heartbeat_at", "DATETIME")
            _add_column(conn, "jobs", columns, "cancel_requested", "BOOLEAN DEFAULT 0")
        if "assets" in tables:
            columns = {column["name"] for column in inspector.get_columns("assets")}
            _add_column(conn, "assets", columns, "cache_key", "VARCHAR(64)")

        # New tables are safe to create idempotently through SQLAlchemy metadata.
        Base.metadata.tables["asset_cache"].create(bind=conn, checkfirst=True)
        Base.metadata.tables["production_runs"].create(bind=conn, checkfirst=True)
        Base.metadata.tables["workspace_accounts"].create(bind=conn, checkfirst=True)
        Base.metadata.tables["workspace_members"].create(bind=conn, checkfirst=True)
        Base.metadata.tables["credit_ledger"].create(bind=conn, checkfirst=True)
        Base.metadata.tables["workspace_subscriptions"].create(bind=conn, checkfirst=True)

        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"))
        row = conn.execute(text("SELECT version FROM schema_version LIMIT 1")).fetchone()
        if row is None:
            conn.execute(text("INSERT INTO schema_version(version) VALUES (:v)"), {"v": SCHEMA_VERSION})
        elif int(row[0]) < SCHEMA_VERSION:
            conn.execute(text("UPDATE schema_version SET version=:v"), {"v": SCHEMA_VERSION})
