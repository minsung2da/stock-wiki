"""Phase 3 API probes — de-risk A4 (dart-fss body shape) and A5 (vchord_bm25 INT[] cast).

These tests are intentionally tiny, run once in Wave 1, and record findings
verbatim to `.planning/phases/03-one-company-walking-skeleton/probe-findings.md`
so downstream plans (04 worker, 05 hybrid_search) can copy the verified
accessor path and SQL.

- Test 1: dart-fss against corp 00126380 (삼성전자) — SLOW, SKIP if no key.
- Test 2: vchord_bm25 `_vchord_bm25_cast_array_to_bm25vector(INT[], -1, true)` cast.
- Test 3: end-to-end BM25 scoring via ix_chunks_bm25 expression index.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa

_PROBE_FINDINGS = Path(".planning/phases/03-one-company-walking-skeleton/probe-findings.md")


def _record_finding(test_name: str, finding: str) -> None:
    """Append-only probe log; never fails the test."""
    try:
        _PROBE_FINDINGS.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        line = f"{ts} test={test_name} finding={finding}\n"
        with _PROBE_FINDINGS.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass  # best-effort; probe log is documentation, not a gate


@pytest.mark.slow
def test_dart_fss_report_body_shape():
    """Probe: dart-fss corp 00126380 (삼성전자) filings A+B — record body accessor shape.

    Skips cleanly if DART_API_KEY env unset. Records the working accessor
    path to probe-findings.md so Plan 04's DART parser can copy verbatim
    (A4 de-risk).
    """
    dart_fss = pytest.importorskip("dart_fss")
    api_key = os.environ.get("DART_API_KEY") or os.environ.get("OPEN_DART_API_KEY")
    if not api_key:
        pytest.skip("DART_API_KEY not set — probe requires live DART API")

    dart_fss.set_api_key(api_key=api_key)
    corp_list = dart_fss.get_corp_list()
    corp = corp_list.find_by_corp_code("00126380")
    assert corp is not None, "corp 00126380 (삼성전자) not in corp list"

    # D-01: pblntf_ty=A (정기) + B (주요사항) only; last 365d slice.
    since = (datetime.utcnow() - timedelta(days=365)).strftime("%Y%m%d")
    filings = corp.search_filings(
        bgn_de=since,
        pblntf_ty=["A", "B"],
        last_reprt_at="Y",
    )
    filings_slice = filings[:1]
    assert len(filings_slice) >= 1, "no A+B filings found for 삼성전자 in past 365d"

    f = filings_slice[0]
    # Minimum-shape assertions on the filing metadata.
    assert isinstance(f.rcept_no, str) and len(f.rcept_no) == 14 and f.rcept_no.isdigit()
    assert isinstance(f.rcept_dt, str) and len(f.rcept_dt) == 8

    # Try the two body-accessor candidates from 03-RESEARCH.md A4.
    body_text = ""
    accessor_used = ""
    try:
        report = f.report  # may be a property or method depending on version
        if callable(report):
            report = report()
        as_dict = report.to_dict() if hasattr(report, "to_dict") else None
        if isinstance(as_dict, dict) and as_dict.get("text"):
            body_text = as_dict["text"]
            accessor_used = "f.report.to_dict()['text']"
    except Exception as e:  # noqa: BLE001
        _record_finding(
            "test_dart_fss_report_body_shape",
            f"report.to_dict() failed: {type(e).__name__}: {e}",
        )

    if not body_text:
        try:
            docs = f.report.get_document() if hasattr(f, "report") else None
            if docs:
                body_text = str(docs)[:200]
                accessor_used = "f.report.get_document()"
        except Exception as e:  # noqa: BLE001
            _record_finding(
                "test_dart_fss_report_body_shape",
                f"report.get_document() failed: {type(e).__name__}: {e}",
            )

    # Record whichever shape worked (or that neither did) for Plan 04.
    _record_finding(
        "test_dart_fss_report_body_shape",
        f"rcept_no={f.rcept_no} rcept_dt={f.rcept_dt} "
        f"accessor={accessor_used!r} body_len={len(body_text)}",
    )
    # Soft assertion: at least one accessor must have produced non-empty text.
    assert body_text, (
        "Neither f.report.to_dict()['text'] nor f.report.get_document() "
        "returned a non-empty body — see probe-findings.md"
    )


def test_vchord_bm25_int_array_cast(pg_with_chunks_row):
    """Probe: bm25_catalog._vchord_bm25_cast_array_to_bm25vector(INT[], -1, true)::text.

    Verifies VectorChord-BM25's implicit-cast function accepts a plain INT[]
    and returns a bm25vector whose textual form is non-empty. Records the
    exact string so Plan 05 can paste verbatim.
    """
    engine = pg_with_chunks_row
    with engine.connect() as conn:
        result = conn.execute(
            sa.text(
                "SELECT bm25_catalog._vchord_bm25_cast_array_to_bm25vector("
                "CAST(:arr AS int[]), -1, true)::text AS result"
            ),
            {"arr": [101, 202, 303]},
        ).scalar()
    assert result is not None and isinstance(result, str) and len(result) > 0
    # NOTE: the text format is whatever vchord_bm25 emits; record it so Plan 05
    # can write matching assertions. Observed format is typically a weighted
    # sparse form like "{101:1.0, 202:1.0, 303:1.0}" or similar.
    _record_finding("test_vchord_bm25_int_array_cast", f"cast_result={result!r}")


def test_bm25_end_to_end_scoring(pg_clean):
    """Probe: insert 3 chunks, run search_bm25query via ix_chunks_bm25 index.

    Covers Pattern 5 copy-paste target SQL.
    """
    doc_id = "b" * 64
    zero_vec = "[" + ",".join(["0"] * 1024) + "]"
    # Canonical end-to-end SQL — Plan 05 hybrid_search ORDER BY clause copies this:
    #
    #   ORDER BY bm25_catalog.search_bm25query(
    #       (c.bm25_tokens)::bm25_catalog.bm25vector,
    #       bm25_catalog.to_bm25query(
    #           'ix_chunks_bm25'::regclass,
    #           CAST(:q AS int[])::bm25_catalog.bm25vector
    #       )
    #   ) DESC
    with pg_clean.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, body, source, vault_path) VALUES (:id, :b, :s, :v)"
            ),
            {"id": doc_id, "b": "x", "s": "dart", "v": "vault/raw/dart/bm25_probe.md"},
        )
        rows = [
            {"doc_id": doc_id, "ord": 0, "text": "a", "emb": zero_vec, "toks": [101, 202]},
            {"doc_id": doc_id, "ord": 1, "text": "b", "emb": zero_vec, "toks": [202, 303]},
            {"doc_id": doc_id, "ord": 2, "text": "c", "emb": zero_vec, "toks": [404, 505]},
        ]
        for r in rows:
            conn.execute(
                sa.text(
                    "INSERT INTO chunks (document_id, ord, text, embedding, bm25_tokens) "
                    "VALUES (:doc_id, :ord, :text, CAST(:emb AS vector), CAST(:toks AS int[]))"
                ),
                r,
            )

    with pg_clean.connect() as conn:
        # Query matching tokens [101, 202] — chunks with those IDs should rank above chunk 3.
        ranked = conn.execute(
            sa.text(
                "SELECT c.ord, bm25_catalog.search_bm25query("
                "  (c.bm25_tokens)::bm25_catalog.bm25vector,"
                "  bm25_catalog.to_bm25query("
                "    'ix_chunks_bm25'::regclass,"
                "    CAST(:q AS int[])::bm25_catalog.bm25vector"
                "  )"
                ") AS score "
                "FROM chunks c "
                "WHERE c.document_id = :doc_id "
                "ORDER BY score DESC NULLS LAST"
            ),
            {"q": [101, 202], "doc_id": doc_id},
        ).all()
    assert len(ranked) == 3
    # At least one chunk must have a non-null score (otherwise the index/query path is broken).
    scores = [r.score for r in ranked]
    assert any(s is not None for s in scores), f"all BM25 scores null: {ranked}"
    _record_finding(
        "test_bm25_end_to_end_scoring",
        f"ranked_orders={[r.ord for r in ranked]} scores={scores}",
    )
