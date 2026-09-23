"""Migration and JSONB round-trip verification in an isolated PostgreSQL container."""

import pytest
from sqlalchemy import inspect, text

from orchestration.jev import review_choices


@pytest.mark.db
def test_migration_and_completed_cache_roundtrip(pg_clean, monkeypatch):
    monkeypatch.setenv("JEV_MODE", "shadow")
    monkeypatch.setenv("JEV_CONFIDENCE_THRESHOLD", "0.8")
    calls = []

    def backend(**kwargs):
        calls.append(kwargs)
        return {
            "model": "jev-test",
            "answers": {
                "relation": {
                    "choice": "supports",
                    "confidence": 0.9,
                    "probabilities": {"supports": 0.9, "insufficient": 0.1},
                }
            },
        }

    kwargs = {
        "task": "migration_test",
        "subject_id": "isolated-1",
        "state": {"source_id": "filing:1", "body": "매출 100억"},
        "questions": {"relation": {"criteria": {"supports": "yes", "insufficient": "no"}}},
        "backend": backend,
    }
    first = review_choices(pg_clean, **kwargs)
    assert first["status"] == "completed"
    second = review_choices(pg_clean, **kwargs)
    assert second["cached"] and len(calls) == 1
    with pg_clean.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT input_payload, result_payload, model FROM jev_reviews "
                    "WHERE review_id=:id"
                ),
                {"id": first["review_id"]},
            )
            .mappings()
            .one()
        )
        assert row["input_payload"]["state"] == kwargs["state"]
        assert row["result_payload"] == first and row["model"] == "jev-test"
    indexes = {item["name"] for item in inspect(pg_clean).get_indexes("jev_reviews")}
    assert {"ix_jev_reviews_lookup", "ix_jev_reviews_created"} <= indexes
