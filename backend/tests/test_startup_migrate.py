"""Startup migration self-heal (app.core.migrate) -- covers the exact
crash-loop scenario reported for pre-Alembic, create_all()-bootstrapped
databases, and confirms a genuinely mismatched legacy schema fails loudly
instead of guessing a revision to stamp.

Each test points Alembic itself at a private temp SQLite file by
monkeypatching app.core.config.get_settings (alembic/env.py reads
get_settings().database_url independently of any engine passed to
migrate.run()), so these never touch the shared tests/test_trustai.db.
"""
from pathlib import Path

import pytest
from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, Text, create_engine, inspect

from app.core import migrate as migrate_module
from app.core.config import Settings
from app.models.db import Base


def _engine_with_patched_settings(tmp_path: Path, monkeypatch, name: str):
    url = f"sqlite:///{tmp_path / name}"
    monkeypatch.setattr("app.core.config.get_settings", lambda: Settings(database_url=url))
    return create_engine(url)


def test_fresh_database_runs_full_migration_chain(tmp_path, monkeypatch):
    engine = _engine_with_patched_settings(tmp_path, monkeypatch, "fresh.db")

    migrate_module.run(engine=engine)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert set(Base.metadata.tables) <= tables
    assert "alembic_version" in tables


def test_already_tracked_database_upgrade_is_a_clean_noop(tmp_path, monkeypatch):
    engine = _engine_with_patched_settings(tmp_path, monkeypatch, "tracked.db")
    migrate_module.run(engine=engine)  # bootstraps from scratch

    migrate_module.run(engine=engine)  # should just be alembic upgrade head, no-op

    inspector = inspect(engine)
    assert set(Base.metadata.tables) <= set(inspector.get_table_names())


def test_pre_alembic_bootstrap_with_matching_schema_self_heals(tmp_path, monkeypatch, capsys):
    engine = _engine_with_patched_settings(tmp_path, monkeypatch, "bootstrap.db")
    Base.metadata.create_all(bind=engine)  # simulates the old create_all()-only startup
    assert "alembic_version" not in inspect(engine).get_table_names()

    migrate_module.run(engine=engine)  # must stamp+upgrade, not crash on CREATE TABLE

    inspector = inspect(engine)
    assert "alembic_version" in inspector.get_table_names()
    assert set(Base.metadata.tables) <= set(inspector.get_table_names())
    assert "stamping at head" in capsys.readouterr().out


def test_pre_alembic_bootstrap_with_mismatched_schema_fails_loudly(tmp_path, monkeypatch, capsys):
    engine = _engine_with_patched_settings(tmp_path, monkeypatch, "legacy.db")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE analyses")

    # Recreate `analyses` matching the *original* initial migration shape --
    # missing risk_score (D-09) and price_plausibility (D-08), the exact
    # partial-schema incident D-11 describes.
    legacy_meta = MetaData()
    Table(
        "analyses",
        legacy_meta,
        Column("id", Integer, primary_key=True),
        Column("listing_id", Integer, nullable=False),  # FK omitted -- irrelevant to column-match detection
        Column("risk_level", String(20), nullable=False),
        Column("summary", Text, nullable=False),
        Column("price_assessment", Text, nullable=False),
        Column("recommendation", String(20), nullable=False),
        Column("seller_questions", JSON, nullable=False),
        Column("model_used", String(120), nullable=False),
        Column("prompt_version", String(20), nullable=False),
        Column("raw_response", Text, nullable=False),
    )
    legacy_meta.create_all(bind=engine)

    with pytest.raises(SystemExit):
        migrate_module.run(engine=engine)

    stderr = capsys.readouterr().err
    assert "risk_score" in stderr
    assert "price_plausibility" in stderr
    assert "refusing to guess" in stderr
    # Confirms it did NOT stamp anything -- no silent guess was made.
    assert "alembic_version" not in inspect(engine).get_table_names()
