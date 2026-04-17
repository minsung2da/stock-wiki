"""Smoke tests for pg_engine and pg_clean fixtures (testcontainers)."""

from __future__ import annotations

import sqlalchemy as sa


def test_pg_engine_reachable(pg_engine) -> None:
    with pg_engine.connect() as conn:
        assert conn.execute(sa.text("SELECT 1")).scalar() == 1


def test_pg_clean_returns_engine(pg_clean) -> None:
    with pg_clean.connect() as conn:
        assert conn.execute(sa.text("SELECT 1")).scalar() == 1
