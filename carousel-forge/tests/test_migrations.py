"""M0 완료 기준: `alembic upgrade head`가 통과하고 모델과 어긋나지 않는다."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

import apps.api.models  # noqa: F401  — 테이블 등록

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "account", "style_dna", "topic_brief", "carousel_set",
    "slide", "asset", "fact_check", "generation_log",
}


def _alembic(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        **dict(__import__("os").environ),
        "CAROUSEL_FORGE_DATABASE_URL": f"sqlite:///{tmp_path / 'test.db'}",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )


def test_upgrade_head_creates_every_table(tmp_path):
    result = _alembic(tmp_path, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES <= tables, EXPECTED_TABLES - tables


def test_migration_matches_models(tmp_path):
    """마이그레이션과 SQLModel 정의가 어긋나면(드리프트) 실패한다."""
    assert _alembic(tmp_path, "upgrade", "head").returncode == 0
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, SQLModel.metadata)
    assert diff == [], f"모델과 마이그레이션이 어긋난다: {diff}"


def test_downgrade_round_trip(tmp_path):
    assert _alembic(tmp_path, "upgrade", "head").returncode == 0
    assert _alembic(tmp_path, "downgrade", "base").returncode == 0
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    remaining = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert remaining == set()
