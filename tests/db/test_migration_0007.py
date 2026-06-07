"""Phase 2 Plan 02-01 Task 3 — schema-shape regression for migration 0007.

These tests introspect the live Postgres testcontainer (already at head per the
``pg_engine`` session fixture) to confirm migration 0007 created the
``decision_cards`` contract locked to ROADMAP SC#1/#2/#6 and
``.planning/research/redesign-2026-05.md`` §3. They run in the default
``pytest -m "not slow and not e2e"`` pass; only ``test_body_tsv_generated``
mutates data (one INSERT via ``seeded_engine`` + ``pg_clean`` CASCADE truncation).

Hard Veto enforcement baked into the assertions:

* Veto #2 — ``expires_at`` is NOT NULL (timed thesis).
* Veto #3 — contradictions live in ``payload`` JSONB (asserted jsonb type).
* Veto #6 — no embedding column on decision_cards (CONTEXT lock).

Coverage map:
* test_decision_cards_shape   — SC#1 (12 columns, PK, FKs, payload jsonb, status CHECK)
* test_decision_cards_indexes — SC#2 (3 mandatory indexes + generated_at DESC)
* test_body_tsv_generated     — SC#6 (tsvector GENERATED STORED + GIN + query match)
* test_orm_round_trip         — drift guard (ORM↔DB parity + 7-table metadata set)
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

# ---------------------------------------------------------------------------
# SC#1 — table shape: 12 locked columns, PK, FKs, payload jsonb, status CHECK
# ---------------------------------------------------------------------------


def test_decision_cards_shape(pg_engine) -> None:
    """decision_cards columns, PK, FKs, payload type, and status CHECK match SC#1."""
    insp = inspect(pg_engine)
    cols = {c["name"]: c for c in insp.get_columns("decision_cards")}

    # All 12 locked columns present.
    for name in (
        "card_id",
        "corp_code",
        "ticker",
        "generated_at",
        "as_of",
        "payload",
        "body_md",
        "status",
        "supersedes",
        "superseded_by",
        "expires_at",
        "schema_version",
    ):
        assert name in cols, f"missing locked column {name!r}; have {sorted(cols)}"

    # PK is card_id.
    pk = insp.get_pk_constraint("decision_cards")
    assert pk["constrained_columns"] == ["card_id"], pk

    # NOT NULL contract on the data-meaningful columns.
    assert cols["card_id"]["nullable"] is False
    assert cols["corp_code"]["nullable"] is False
    assert cols["generated_at"]["nullable"] is False
    assert cols["as_of"]["nullable"] is False
    assert cols["payload"]["nullable"] is False
    assert cols["body_md"]["nullable"] is False
    assert cols["status"]["nullable"] is False
    assert cols["expires_at"]["nullable"] is False  # Veto #2: timed thesis
    assert cols["schema_version"]["nullable"] is False
    # Nullable pointers / optional fields.
    assert cols["ticker"]["nullable"] is True
    assert cols["supersedes"]["nullable"] is True
    assert cols["superseded_by"]["nullable"] is True

    # corp_code FK → entities(corp_code).
    fks = insp.get_foreign_keys("decision_cards")
    fk_corp = [fk for fk in fks if fk["constrained_columns"] == ["corp_code"]]
    assert len(fk_corp) == 1, f"expected one corp_code FK, got {fks}"
    assert fk_corp[0]["referred_table"] == "entities"
    assert fk_corp[0]["referred_columns"] == ["corp_code"]

    # Self-referential FKs: supersedes + superseded_by → decision_cards(card_id) SET NULL.
    for col in ("supersedes", "superseded_by"):
        fk_self = [fk for fk in fks if fk["constrained_columns"] == [col]]
        assert len(fk_self) == 1, f"expected one {col} FK, got {fks}"
        assert fk_self[0]["referred_table"] == "decision_cards"
        assert fk_self[0]["referred_columns"] == ["card_id"]
        options = fk_self[0].get("options") or {}
        assert options.get("ondelete", "").upper() == "SET NULL", fk_self[0]

    # payload is jsonb.
    with pg_engine.connect() as conn:
        payload_typ = conn.execute(
            sa.text(
                "SELECT format_type(atttypid, atttypmod) "
                "FROM pg_attribute "
                "WHERE attrelid = 'decision_cards'::regclass "
                "  AND attname = 'payload' "
                "  AND NOT attisdropped"
            )
        ).scalar()
    assert payload_typ == "jsonb", f"expected jsonb, got {payload_typ!r}"

    # status CHECK constraint enumerates the three allowed values.
    with pg_engine.connect() as conn:
        ck = conn.execute(
            sa.text(
                "SELECT pg_get_constraintdef(c.oid) "
                "FROM pg_constraint c "
                "WHERE c.conrelid = 'decision_cards'::regclass "
                "  AND c.contype = 'c' "
                "  AND c.conname = 'ck_decision_cards_status'"
            )
        ).scalar()
    assert ck is not None, "ck_decision_cards_status missing"
    for value in ("active", "superseded", "invalidated"):
        assert value in ck, f"missing {value!r} in {ck}"

    # Veto #6 — no embedding column on decision_cards.
    assert "body_embedding" not in cols, "decision_cards must NOT carry an embedding (Veto #6)"


# ---------------------------------------------------------------------------
# SC#2 — mandatory indexes + generated_at DESC ordering
# ---------------------------------------------------------------------------


def test_decision_cards_indexes(pg_engine) -> None:
    """The 3 SC#2 indexes exist and the composite carries generated_at DESC."""
    insp = inspect(pg_engine)
    idx_names = {i["name"] for i in insp.get_indexes("decision_cards")}

    assert "ix_decision_cards_corp_status_gen" in idx_names
    assert "ix_decision_cards_supersedes" in idx_names
    assert "ix_decision_cards_expires" in idx_names

    # Composite index orders generated_at DESC.
    with pg_engine.connect() as conn:
        idxdef = conn.execute(
            sa.text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'decision_cards' "
                "  AND indexname = 'ix_decision_cards_corp_status_gen'"
            )
        ).scalar()
    assert idxdef is not None, "ix_decision_cards_corp_status_gen missing"
    assert "generated_at DESC" in idxdef, idxdef


# ---------------------------------------------------------------------------
# SC#6 — body_tsv GENERATED STORED tsvector + GIN index + query-matchable
# ---------------------------------------------------------------------------


def test_body_tsv_generated(seeded_engine) -> None:
    """body_tsv is a STORED GENERATED tsvector, GIN-indexed, and query-matchable."""
    engine = seeded_engine

    # Column type is tsvector.
    with engine.connect() as conn:
        typ = conn.execute(
            sa.text(
                "SELECT format_type(atttypid, atttypmod) "
                "FROM pg_attribute "
                "WHERE attrelid = 'decision_cards'::regclass "
                "  AND attname = 'body_tsv' "
                "  AND NOT attisdropped"
            )
        ).scalar()
    assert typ == "tsvector", f"expected tsvector, got {typ!r}"

    # attgenerated = 's' confirms a STORED generated column.
    with engine.connect() as conn:
        attgen = conn.execute(
            sa.text(
                "SELECT attgenerated FROM pg_attribute "
                "WHERE attrelid = 'decision_cards'::regclass "
                "  AND attname = 'body_tsv' "
                "  AND NOT attisdropped"
            )
        ).scalar()
    assert attgen == "s", f"expected stored-generated ('s'), got {attgen!r}"

    # GIN index over body_tsv.
    with engine.connect() as conn:
        gin_def = conn.execute(
            sa.text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'decision_cards' "
                "  AND indexname = 'ix_decision_cards_body_tsv'"
            )
        ).scalar()
    assert gin_def is not None, "ix_decision_cards_body_tsv missing"
    assert "gin" in gin_def.lower(), gin_def

    # Insert one card (app writes body_md only; body_tsv is auto-generated) and
    # confirm a to_tsquery('simple', ...) match returns the row. Bind params only.
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO decision_cards "
                "(card_id, corp_code, ticker, generated_at, as_of, payload, "
                " body_md, expires_at) "
                "VALUES (:card_id, :corp_code, :ticker, :generated_at, :as_of, "
                "        CAST(:payload AS jsonb), :body_md, :expires_at)"
            ),
            {
                "card_id": "card_005930_tsvtest",
                "corp_code": "00126380",
                "ticker": "005930",
                "generated_at": "2026-05-28T17:42:00+09:00",
                "as_of": "2026-05-28T16:00:00+09:00",
                "payload": '{"decision": {"stance": "HOLD"}}',
                "body_md": "Samsung memory demand recovery narrative.",
                "expires_at": "2026-06-15T00:00:00+09:00",
            },
        )

    with engine.connect() as conn:
        matched = conn.execute(
            sa.text(
                "SELECT card_id FROM decision_cards WHERE body_tsv @@ to_tsquery('simple', :word)"
            ),
            {"word": "memory"},
        ).scalar()
    assert matched == "card_005930_tsvtest", f"body_tsv did not match; got {matched!r}"


# ---------------------------------------------------------------------------
# Drift guard — ORM ↔ DB column-set parity + full 7-table metadata set
# ---------------------------------------------------------------------------


def test_orm_round_trip(pg_engine) -> None:
    """Every ORM model's declared columns match the live DB column set.

    Safety net catching drift between migration 0006/0007 (DDL authors) and
    ``src/db/entity_models.py``. The metadata table set is now seven tables
    including ``decision_cards``.
    """
    from db.entity_models import (
        OHLCV,
        Base,
        CollectorRun,
        DecisionCard,
        Event,
        Filing,
        MacroSeries,
        News,
    )

    insp = inspect(pg_engine)
    for model in (Filing, News, OHLCV, MacroSeries, Event, CollectorRun, DecisionCard):
        table_name = model.__tablename__
        db_cols = {c["name"] for c in insp.get_columns(table_name)}
        orm_cols = {c.name for c in model.__table__.columns}
        missing = orm_cols - db_cols
        extra = db_cols - orm_cols
        assert not missing, f"{table_name}: ORM declares columns absent from DB: {sorted(missing)}"
        assert not extra, f"{table_name}: DB has columns not declared in ORM: {sorted(extra)}"

    # Base.metadata table set matches the nine v2.0 ORM tables (Phase 3 added
    # notes + fundamentals on the same shared Base — migration 0008).
    assert set(Base.metadata.tables) == {
        "filings",
        "news",
        "ohlcv",
        "macro_series",
        "events",
        "collector_runs",
        "decision_cards",
        "notes",
        "fundamentals",
    }
