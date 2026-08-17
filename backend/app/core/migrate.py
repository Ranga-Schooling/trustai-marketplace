"""Startup migration runner — self-heals the one legacy-schema failure mode
that has actually happened (D-11, docs/DESIGN_NOTES.md): a Postgres database
bootstrapped by `Base.metadata.create_all()` before Alembic was wired into
the Dockerfile has every table Alembic's initial revision would create, but
no `alembic_version` row. `alembic upgrade head` then tries to `CREATE TABLE
users` on a table that already exists and crashes -- and since this runs as
the container's startup CMD, that's a permanent crash-loop with no automated
recovery (see the "API container crash-loops" issue).

Deliberately narrow: this only auto-stamps when the existing tables' columns
are an *exact* match for what the current models expect. That's the one case
where stamping is verifiably safe -- it means the database was bootstrapped
from these exact models, just never touched by Alembic. Any other mismatch
(a genuinely older, partial schema, the D-11 incident's original shape)
is NOT guessed at: guessing wrong and stamping at the wrong revision would
silently skip a real ALTER TABLE and leave the app querying columns that
don't exist, which is worse than the crash it's meant to fix. That case
still fails, but with a message naming exactly what doesn't match instead
of a bare psycopg2 traceback -- see docs/DESIGN_NOTES.md D-11 for how the
one real occurrence of this was diagnosed and fixed by hand.
"""
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.models.db import Base
from app.models.db import engine as default_engine

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


def _existing_tables_match_models(inspector, expected_tables: list[str]) -> tuple[bool, str]:
    """Return (matches, detail). `matches` is True only if every expected
    table exists with exactly the column set the current models define."""
    mismatches = []
    for table_name in expected_tables:
        actual_columns = {col["name"] for col in inspector.get_columns(table_name)}
        expected_columns = set(Base.metadata.tables[table_name].columns.keys())
        if actual_columns != expected_columns:
            missing = expected_columns - actual_columns
            extra = actual_columns - expected_columns
            mismatches.append(f"{table_name}: missing={sorted(missing)} extra={sorted(extra)}")
    if mismatches:
        return False, "; ".join(mismatches)
    return True, ""


def run(engine=None) -> None:
    """`engine` is injectable for tests; production callers (the Dockerfile
    CMD) always use the default, settings-derived engine. Alembic itself
    (alembic/env.py) always targets `get_settings().database_url`
    independently, so tests that pass a non-default `engine` must also
    monkeypatch `app.core.config.get_settings` to the same URL."""
    engine = engine or default_engine
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    expected_tables = list(Base.metadata.tables.keys())
    cfg = _alembic_config()

    has_alembic_version = "alembic_version" in existing_tables
    has_any_expected_table = bool(existing_tables & set(expected_tables))

    if has_alembic_version or not has_any_expected_table:
        # Normal case: either Alembic already tracks this database, or it's
        # empty and the full migration chain runs from scratch. No special
        # handling needed either way.
        command.upgrade(cfg, "head")
        return

    # alembic_version is missing but some/all expected tables already exist
    # -- the create_all()-before-Alembic scenario. Only self-heal if it's
    # verifiably safe to do so.
    tables_present = [t for t in expected_tables if t in existing_tables]
    matches, detail = _existing_tables_match_models(inspector, tables_present)

    if len(tables_present) != len(expected_tables) or not matches:
        print(
            "Startup migration: found tables with no alembic_version row, but "
            "they don't exactly match the current models -- refusing to guess "
            "which revision to stamp (a wrong guess would silently skip real "
            "schema changes). This is the scenario documented in "
            "docs/DESIGN_NOTES.md D-11: diagnose the actual schema (see which "
            "columns are missing below) and fix with a manual "
            "`alembic stamp <matching-revision>` before restarting.\n"
            f"Expected tables: {sorted(expected_tables)}\n"
            f"Existing tables: {sorted(existing_tables & set(expected_tables))}\n"
            f"Column mismatches: {detail or '(table set itself differs)'}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(
        "Startup migration: existing tables exactly match current models but "
        "have no alembic_version row (pre-Alembic create_all() bootstrap) -- "
        "stamping at head instead of crash-looping on CREATE TABLE.",
    )
    command.stamp(cfg, "head")
    command.upgrade(cfg, "head")


if __name__ == "__main__":
    run()
