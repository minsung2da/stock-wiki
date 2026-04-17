"""Tests for src/stock_mcp/search_core.py (hybrid RRF retrieval).

These tests exercise the SQL path end-to-end against the testcontainer
Postgres from ``pg_clean`` with deterministic fake embeddings + fake
bm25_tokens so we can force dense-only / bm25-only rankings and verify
RRF fusion numerically.

Fakes: ``encode_query`` and ``tokenize_ko`` are monkeypatched per-test.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from stock_mcp import search_core
from stock_mcp.errors import ErrorCode, StructuredError
from stock_mcp.models import DateRange

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DIM = 1024


def _vec(unit_index: int) -> list[float]:
    """Return a 1024-d unit vector with a 1.0 in slot ``unit_index``."""
    v = [0.0] * _DIM
    v[unit_index % _DIM] = 1.0
    return v


def _vec_lit(unit_index: int) -> str:
    return "[" + ",".join(repr(float(x)) for x in _vec(unit_index)) + "]"


def _insert_doc(
    conn: sa.Connection,
    *,
    doc_id: str,
    vault_path: str,
    source: str = "dart",
    corp_code: str | None = None,
    first_seen: date | None = None,
) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO documents "
            "(id, body, source, vault_path, corp_code, first_seen_at, last_seen_at) "
            "VALUES (:id, :body, :source, :vp, :cc, "
            "COALESCE(:fs, now()), COALESCE(:fs, now()))"
        ),
        {
            "id": doc_id,
            "body": "body",
            "source": source,
            "vp": vault_path,
            "cc": corp_code,
            "fs": first_seen,
        },
    )


def _insert_chunk(
    conn: sa.Connection,
    *,
    doc_id: str,
    ord_: int,
    text: str,
    vec_slot: int,
    bm25_tokens: list[int],
) -> int:
    row = conn.execute(
        sa.text(
            "INSERT INTO chunks "
            "(document_id, ord, text, embedding_model, embedding, "
            " section_path, section_index, bm25_tokens) "
            "VALUES (:doc_id, :ord, :text, :em, CAST(:emb AS vector), "
            " :sp, :si, CAST(:toks AS int[])) RETURNING id"
        ),
        {
            "doc_id": doc_id,
            "ord": ord_,
            "text": text,
            "em": "BAAI/bge-m3@v1",
            "emb": _vec_lit(vec_slot),
            "sp": "root",
            "si": 0,
            "toks": bm25_tokens,
        },
    ).first()
    return int(row.id)


def _seed_search_corpus(engine: Engine) -> dict[str, Any]:
    """Seed 5 documents × 3 chunks with predictable embeddings and tokens.

    Returns a map of named fixture chunk-ids for tests to assert on.
    """
    state: dict[str, Any] = {}
    with engine.begin() as conn:
        # Doc 1 — Samsung (corp 00126380), DART
        d1 = "1" * 64
        _insert_doc(
            conn,
            doc_id=d1,
            vault_path="vault/raw/dart/samsung_a.md",
            corp_code="00126380",
            source="dart",
            first_seen=date(2026, 1, 10),
        )
        for i in range(3):
            _insert_chunk(
                conn,
                doc_id=d1,
                ord_=i,
                text=f"samsung doc-1 chunk-{i}",
                vec_slot=100 + i,
                bm25_tokens=[1001, 1002, 1003, i],
            )
        # Doc 2 — Samsung, news
        d2 = "2" * 64
        _insert_doc(
            conn,
            doc_id=d2,
            vault_path="vault/raw/news/samsung_b.md",
            corp_code="00126380",
            source="news",
            first_seen=date(2026, 2, 20),
        )
        for i in range(3):
            _insert_chunk(
                conn,
                doc_id=d2,
                ord_=i,
                text=f"samsung news chunk-{i}",
                vec_slot=200 + i,
                bm25_tokens=[2001, 2002, i],
            )
        # Doc 3 — SK hynix (corp 00164779), DART
        d3 = "3" * 64
        _insert_doc(
            conn,
            doc_id=d3,
            vault_path="vault/raw/dart/hynix.md",
            corp_code="00164779",
            source="dart",
            first_seen=date(2026, 1, 15),
        )
        for i in range(3):
            _insert_chunk(
                conn,
                doc_id=d3,
                ord_=i,
                text=f"hynix chunk-{i}",
                vec_slot=300 + i,
                bm25_tokens=[3001, 3002, i],
            )
        # Doc 4 — Generic news, no corp_code
        d4 = "4" * 64
        _insert_doc(
            conn,
            doc_id=d4,
            vault_path="vault/raw/news/macro.md",
            corp_code=None,
            source="news",
            first_seen=date(2026, 3, 5),
        )
        for i in range(3):
            _insert_chunk(
                conn,
                doc_id=d4,
                ord_=i,
                text=f"macro chunk-{i}",
                vec_slot=400 + i,
                bm25_tokens=[4001, 4002, i],
            )
        # Doc 5 — Probe doc with ONE chunk strong in dense (slot 0) and ONE
        # chunk strong in bm25 (tokens match query). Used for RRF test.
        d5 = "5" * 64
        _insert_doc(
            conn,
            doc_id=d5,
            vault_path="vault/raw/dart/rrf_probe.md",
            corp_code="00126380",
            source="dart",
            first_seen=date(2026, 2, 1),
        )
        state["dense_winner_cid"] = _insert_chunk(
            conn,
            doc_id=d5,
            ord_=0,
            text="dense winner",
            vec_slot=0,  # exact match to _vec(0)
            bm25_tokens=[9999],  # bm25 miss
        )
        state["bm25_winner_cid"] = _insert_chunk(
            conn,
            doc_id=d5,
            ord_=1,
            text="bm25 winner",
            vec_slot=999,  # dense miss (orthogonal)
            # High frequency of token 1001 → BM25 ranks this #1 for query [1001].
            bm25_tokens=[1001, 1001, 1001, 1001, 1001, 1001, 1001, 1001],
        )
        state["dumb_cid"] = _insert_chunk(
            conn,
            doc_id=d5,
            ord_=2,
            text="irrelevant",
            vec_slot=998,
            bm25_tokens=[6000, 6001],
        )
    return state


# ---------------------------------------------------------------------------
# Monkeypatch helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_embed(monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch encode_query to return _vec(0) by default."""
    calls: list[str] = []

    def _fake(q: str) -> tuple[float, ...]:
        calls.append(q)
        return tuple(_vec(0))

    monkeypatch.setattr(search_core, "encode_query", _fake)
    return calls


@pytest.fixture
def fake_tokenize(monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch tokenize_ko to return tokens that exist in the seed corpus."""

    def _fake(q: str) -> list[int]:
        # 1001 is a token that appears in doc1 chunks and (by construction)
        # with high frequency in the bm25 winner chunk.
        return [1001]

    monkeypatch.setattr(search_core, "tokenize_ko", _fake)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("fake_embed", "fake_tokenize")
class TestHybridSearch:
    """All tests in this class use the pg_clean fixture (DB)."""

    def test_build_filter_clause_ticker_to_corp_code(self, pg_clean: Engine) -> None:
        """H1 — ticker='005930' resolves to corp_code='00126380' (Samsung)."""
        with pg_clean.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO entities (corp_code, canonical_name, current_ticker) "
                    "VALUES (:cc, :name, :tk)"
                ),
                {"cc": "00126380", "name": "삼성전자", "tk": "005930"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO entity_aliases (corp_code, kind, value, valid_from, valid_to) "
                    "VALUES (:cc, 'ticker', :v, :vf, NULL)"
                ),
                {"cc": "00126380", "v": "005930", "vf": date(2020, 1, 1)},
            )
        params = search_core.build_filter_clause("005930", None, None, pg_clean, as_of=None)
        assert params["corp_code"] == "00126380"
        assert params["source"] is None
        assert params["date_from"] is None
        assert params["date_to"] is None

    def test_hybrid_search_returns_expected_shape(self, pg_clean: Engine) -> None:
        """H2 — top_k=3 returns 3 dicts with the canonical key set."""
        _seed_search_corpus(pg_clean)
        hits = search_core.hybrid_search(pg_clean, "q", mode="hybrid", top_k=3)
        assert len(hits) == 3
        required = {"chunk_id", "rrf_score", "vault_path", "text", "source", "document_id"}
        for h in hits:
            assert required.issubset(h.keys())

    def test_hybrid_rrf_fusion(self, pg_clean: Engine) -> None:
        """H3 — dense winner + bm25 winner both appear; RRF score > 0."""
        state = _seed_search_corpus(pg_clean)
        hits = search_core.hybrid_search(pg_clean, "q", mode="hybrid", top_k=50)
        cid_to_score = {h["chunk_id"]: h["rrf_score"] for h in hits}
        assert state["dense_winner_cid"] in cid_to_score
        assert state["bm25_winner_cid"] in cid_to_score
        # Every returned RRF score must come from at least one CTE's 1/(60+rk)
        # contribution, so is strictly positive.
        assert all(score > 0 for score in cid_to_score.values())
        # Dense winner (slot 0 — exact query match) must outscore a chunk that
        # loses both CTEs (the "dumb" chunk with orthogonal vec + no token hit).
        assert cid_to_score[state["dense_winner_cid"]] >= cid_to_score.get(state["dumb_cid"], 0.0)

    def test_mode_semantic_only(self, pg_clean: Engine) -> None:
        """H4 — mode='semantic' uses dense-only SQL (sparse ignored)."""
        state = _seed_search_corpus(pg_clean)
        hits = search_core.hybrid_search(pg_clean, "q", mode="semantic", top_k=5)
        # bm25-only winner has orthogonal embedding → its dense rank is far
        # from #1; it should not dominate the top spots.
        cids = [h["chunk_id"] for h in hits]
        # The dense winner (slot 0) must be ranked first.
        assert cids[0] == state["dense_winner_cid"]

    def test_mode_bm25_only(self, pg_clean: Engine) -> None:
        """H5 — mode='bm25' uses sparse-only SQL (dense ignored)."""
        state = _seed_search_corpus(pg_clean)
        hits = search_core.hybrid_search(pg_clean, "q", mode="bm25", top_k=5)
        cids = [h["chunk_id"] for h in hits]
        # BM25 winner has tokens matching the query → ranks #1.
        assert cids[0] == state["bm25_winner_cid"]

    def test_ticker_filter_applied_pre_scan(self, pg_clean: Engine) -> None:
        """H6 — ticker restricts results to that corp's documents only."""
        with pg_clean.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO entities (corp_code, canonical_name, current_ticker) "
                    "VALUES ('00126380', '삼성전자', '005930')"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO entity_aliases (corp_code, kind, value, valid_from) "
                    "VALUES ('00126380', 'ticker', '005930', :vf)"
                ),
                {"vf": date(2020, 1, 1)},
            )
        _seed_search_corpus(pg_clean)
        hits = search_core.hybrid_search(pg_clean, "q", ticker="005930", mode="hybrid", top_k=20)
        # Every hit's document_id must be a Samsung doc (d1, d2, d5).
        samsung_ids = {"1" * 64, "2" * 64, "5" * 64}
        for h in hits:
            assert h["document_id"] in samsung_ids

    def test_ticker_filter_excludes_other_companies(self, pg_clean: Engine) -> None:
        """H15 — Samsung ticker MUST exclude SK hynix chunks entirely."""
        with pg_clean.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO entities (corp_code, canonical_name, current_ticker) "
                    "VALUES ('00126380', '삼성전자', '005930')"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO entity_aliases (corp_code, kind, value, valid_from) "
                    "VALUES ('00126380', 'ticker', '005930', :vf)"
                ),
                {"vf": date(2020, 1, 1)},
            )
        _seed_search_corpus(pg_clean)
        hits = search_core.hybrid_search(pg_clean, "q", ticker="005930", mode="hybrid", top_k=50)
        hynix_id = "3" * 64
        assert all(h["document_id"] != hynix_id for h in hits)

    def test_source_filter_applied(self, pg_clean: Engine) -> None:
        """H7 — source='dart' excludes non-DART rows."""
        _seed_search_corpus(pg_clean)
        hits = search_core.hybrid_search(pg_clean, "q", source="dart", mode="hybrid", top_k=20)
        for h in hits:
            assert h["source"] == "dart"

    def test_date_range_filter_applied(self, pg_clean: Engine) -> None:
        """H8 — date_range restricts on documents.first_seen_at."""
        _seed_search_corpus(pg_clean)
        hits = search_core.hybrid_search(
            pg_clean,
            "q",
            date_range=DateRange(start="2026-02-01", end="2026-03-01"),
            mode="hybrid",
            top_k=20,
        )
        # Only d2 (Feb 20) + d5 (Feb 1) fall in [Feb 1, Mar 1); d1 (Jan 10),
        # d3 (Jan 15), d4 (Mar 5) excluded.
        doc_ids = {h["document_id"] for h in hits}
        assert doc_ids <= {"2" * 64, "5" * 64}

    def test_top_k_capped_at_50(self, pg_clean: Engine) -> None:
        """H9 — top_k=999 clamped to 50 (D-10)."""
        _seed_search_corpus(pg_clean)
        hits = search_core.hybrid_search(pg_clean, "q", mode="hybrid", top_k=999)
        assert len(hits) <= 50

    def test_iterative_scan_session_set(self, pg_clean: Engine) -> None:
        """H10 — the module-level SQL constant sets iterative_scan."""
        _seed_search_corpus(pg_clean)
        # Direct source check: the GUC SET is a module constant, and the
        # function calls it. Run a search (smoke) + assert the constant text.
        text_str = str(search_core._SESSION_SET_ITERATIVE_SCAN)
        assert "hnsw.iterative_scan" in text_str
        assert "relaxed_order" in text_str
        # And a smoke call still succeeds (proves the SET survives runtime).
        search_core.hybrid_search(pg_clean, "q", mode="hybrid", top_k=3)

    def test_resolve_entity_ticker_recycle_respected(self, pg_clean: Engine) -> None:
        """H11 — as_of in the OLD corp's window returns the old corp_code."""
        with pg_clean.begin() as conn:
            # Old corp OLDCORPA (delisted), new corp NEWCORPA (current) both
            # held ticker '111111' at different times.
            conn.execute(
                sa.text(
                    "INSERT INTO entities (corp_code, canonical_name, current_ticker) "
                    "VALUES ('OLD00001', 'OldCo', NULL), "
                    "       ('NEW00002', 'NewCo', '111111')"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO entity_aliases "
                    "(corp_code, kind, value, valid_from, valid_to) VALUES "
                    "('OLD00001','ticker','111111',:vf_old,:vt_old), "
                    "('NEW00002','ticker','111111',:vf_new,NULL)"
                ),
                {
                    "vf_old": date(2015, 1, 1),
                    "vt_old": date(2020, 1, 1),
                    "vf_new": date(2020, 1, 1),
                },
            )
        # as_of in OLD window → OLD corp
        params_old = search_core.build_filter_clause(
            "111111", None, None, pg_clean, as_of=date(2017, 6, 1)
        )
        assert params_old["corp_code"] == "OLD00001"
        # as_of in NEW window → NEW corp
        params_new = search_core.build_filter_clause(
            "111111", None, None, pg_clean, as_of=date(2022, 6, 1)
        )
        assert params_new["corp_code"] == "NEW00002"

    def test_excerpt_wrapped_in_vault_excerpt(self, pg_clean: Engine) -> None:
        """H12 — each hit's excerpt uses the <untrusted> wrapper (D-17)."""
        _seed_search_corpus(pg_clean)
        hits = search_core.hybrid_search(pg_clean, "q", mode="hybrid", top_k=3)
        for h in hits:
            assert h["excerpt"].startswith("<untrusted ")
            assert h["excerpt"].rstrip().endswith("</untrusted>")

    def test_excerpt_length_capped(self, pg_clean: Engine) -> None:
        """H13 — each excerpt's INNER text ≤ 400 chars."""
        # Seed a single doc with a very long chunk.
        with pg_clean.begin() as conn:
            _insert_doc(
                conn,
                doc_id="a" * 64,
                vault_path="vault/raw/dart/long.md",
                source="dart",
            )
            _insert_chunk(
                conn,
                doc_id="a" * 64,
                ord_=0,
                text="X" * 2000,  # well past 400
                vec_slot=0,
                bm25_tokens=[7777],
            )
        hits = search_core.hybrid_search(pg_clean, "q", mode="hybrid", top_k=1)
        assert len(hits) == 1
        inner = hits[0]["excerpt"].split(">", 1)[1].rsplit("<", 1)[0].strip()
        assert len(inner) <= 400

    def test_invalid_ticker_raises_structured_error(self, pg_clean: Engine) -> None:
        """H14 — non-digit ticker raises StructuredError(INVALID_TICKER)."""
        with pytest.raises(StructuredError) as exc:
            search_core.hybrid_search(pg_clean, "q", ticker="abc", mode="hybrid")
        assert exc.value.code == ErrorCode.INVALID_TICKER

    def test_unresolved_ticker_raises_invalid_ticker(self, pg_clean: Engine) -> None:
        """H14b — valid-shape ticker with no entity also raises INVALID_TICKER."""
        with pytest.raises(StructuredError) as exc:
            search_core.hybrid_search(pg_clean, "q", ticker="999999", mode="hybrid")
        assert exc.value.code == ErrorCode.INVALID_TICKER
