"""Separate, append-only audit storage for advisory Jev reviews."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

metadata = sa.MetaData()
jev_reviews = sa.Table(
    "jev_reviews",
    metadata,
    sa.Column("review_id", sa.String(36), primary_key=True),
    sa.Column("task", sa.Text, nullable=False),
    sa.Column("subject_id", sa.Text, nullable=False),
    sa.Column("input_hash", sa.String(64), nullable=False),
    sa.Column("model", sa.Text, nullable=False),
    sa.Column("prompt_version", sa.Text, nullable=False),
    sa.Column("mode", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("threshold", sa.Float, nullable=False),
    sa.Column("input_payload", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
    sa.Column("result_payload", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
    sa.Column("request_id", sa.Text),
    sa.Column("usage", sa.JSON().with_variant(JSONB, "postgresql")),
    sa.Column("error_code", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('completed', 'error')", name="ck_jev_reviews_status"),
    sa.CheckConstraint("mode IN ('off', 'shadow')", name="ck_jev_reviews_mode"),
    sa.CheckConstraint("threshold >= 0 AND threshold <= 1", name="ck_jev_reviews_threshold"),
)
sa.Index(
    "ix_jev_reviews_lookup",
    jev_reviews.c.task,
    jev_reviews.c.subject_id,
    jev_reviews.c.input_hash,
    jev_reviews.c.status,
)
sa.Index("ix_jev_reviews_created", jev_reviews.c.created_at)


def find_completed(
    engine: Engine,
    *,
    task: str,
    subject_id: str,
    input_hash: str,
) -> dict[str, Any] | None:
    """Reuse only successful, identically fingerprinted reviews."""
    with engine.connect() as conn:
        result = conn.execute(
            sa.select(jev_reviews.c.result_payload)
            .where(
                jev_reviews.c.task == task,
                jev_reviews.c.subject_id == subject_id,
                jev_reviews.c.input_hash == input_hash,
                jev_reviews.c.status == "completed",
            )
            .order_by(jev_reviews.c.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    return dict(result) if result is not None else None


def insert_review(engine: Engine, values: dict[str, Any]) -> None:
    """Write one attempt transactionally; callers must surface storage failures."""
    with engine.begin() as conn:
        conn.execute(jev_reviews.insert().values(**values))
