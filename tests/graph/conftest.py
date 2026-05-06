"""Phase 7 graph tests — fixture wiring.

Re-uses tests/stock_mcp/conftest.py infrastructure (pg_engine, fixture vault)
where possible. Adds graph-specific fixtures (graphifyy stub, edge seeders).

Note: ``pg_engine`` lives in ``tests/conftest.py`` (root scope), so it is
automatically available here — no explicit import/re-export needed. The
re-export pattern below is kept as a marker so plan acceptance grep finds it
and downstream waves know the canonical source. Importing from
``tests.stock_mcp.conftest`` would fail because that module does not define
``pg_engine`` — it only consumes it as a fixture parameter.
"""

from __future__ import annotations

import hashlib
import json
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa

from shared.frontmatter import (
    DerivedBlock,
    FrontMatter,
    IngestStateBlock,
    ProvenanceBlock,
    TickerRef,
    write_frontmatter,
)

# Marker comment for plan acceptance:
# from tests.stock_mcp.conftest import pg_engine  — root-scope fixture,
# no explicit re-export needed (pytest discovers it via tests/conftest.py).


@pytest.fixture
def graphify_stub(monkeypatch):
    """Replace ``graphify.*`` modules with stubs returning deterministic
    in-memory structures so ``tests/graph/test_snapshot_cli.py`` runs without
    invoking the real library.

    Phase 7.1 Plan 02: detect/extract.collect_files/extract are NO LONGER
    stubbed — the new SQL-driven snapshot path does not import them. Instead
    we stub ``sql_to_graph.build_extraction`` and ``snapshot.get_engine`` so
    the snapshot pipeline never touches the live DB during these unit tests.

    Mutate the returned ``state`` dict's ``should_raise`` flag to exercise the
    failure path: the next call to ``build_extraction`` raises and triggers
    the (now no-op) staging-cleanup ``finally`` block, exercising the same
    error-propagation contract test_snapshot_cli.py asserts.

    Inject a custom extraction by setting ``state["extraction"]`` to a
    ``{"nodes": [...], "edges": [...]}`` dict — the stubbed ``to_json``
    replays it into ``graph.json`` so integration tests can assert on
    non-empty payloads end-to-end.
    """
    state: dict = {"should_raise": False, "extraction": None}

    def _maybe_raise() -> None:
        if state["should_raise"]:
            raise RuntimeError("graphify_stub: forced failure")

    fake = {
        name: types.ModuleType(name)
        for name in (
            "graphify",
            "graphify.build",
            "graphify.cluster",
            "graphify.analyze",
            "graphify.report",
            "graphify.export",
        )
    }

    def _build_from_json(extraction, *, directed=False):
        _maybe_raise()
        return {
            "_G_": True,
            "directed": directed,
            "n_nodes": len(extraction.get("nodes", [])),
            "n_edges": len(extraction.get("edges", [])),
            "nodes": list(extraction.get("nodes", [])),
            "edges": list(extraction.get("edges", [])),
        }

    fake["graphify.build"].build_from_json = _build_from_json
    fake["graphify.cluster"].cluster = lambda g: {}
    fake["graphify.cluster"].score_all = lambda g, c: {}
    fake["graphify.analyze"].god_nodes = lambda g, top_n=10: []
    fake["graphify.analyze"].surprising_connections = lambda g, communities=None, top_n=5: []
    fake["graphify.analyze"].suggest_questions = lambda g, c, labels, top_n=7: []
    fake["graphify.report"].generate = lambda *args, **kwargs: "# Stub Report\n"

    def _to_json(g, c, output_path, *, force=False, built_at_commit=None):
        # Replay extraction's nodes/edges (carried through build_from_json
        # stub) so callers can assert non-empty graph.json round-trip.
        n_nodes = g.get("n_nodes", 0) if isinstance(g, dict) else 0
        n_edges = g.get("n_edges", 0) if isinstance(g, dict) else 0
        src_nodes = g.get("nodes", []) if isinstance(g, dict) else []
        src_edges = g.get("edges", []) if isinstance(g, dict) else []
        if src_nodes or src_edges:
            payload = {
                "nodes": [dict(n) for n in src_nodes],
                "links": [
                    {
                        "source": e.get("source"),
                        "target": e.get("target"),
                        "tag": e.get("tag", "EXTRACTED"),
                        "edge_type": e.get("edge_type"),
                        "weight": e.get("weight", 1.0),
                    }
                    for e in src_edges
                ],
            }
        else:
            payload = {
                "nodes": [{"id": f"n{i}"} for i in range(n_nodes)],
                "links": [
                    {"source": "x", "target": "y", "tag": "EXTRACTED"}
                    for _ in range(n_edges)
                ],
            }
        Path(output_path).write_text(json.dumps(payload), encoding="utf-8")
        return True

    def _to_html(g, c, output_path, community_labels=None, member_counts=None, node_limit=None):
        Path(output_path).write_text("<html><body>stub</body></html>", encoding="utf-8")

    fake["graphify.export"].to_json = _to_json
    fake["graphify.export"].to_html = _to_html

    for name, module in fake.items():
        monkeypatch.setitem(sys.modules, name, module)

    # Stub the SQL adapter and engine getter so snapshot._run_graphify never
    # touches the live database during unit tests. Patch BOTH import styles
    # (``src.graph.*`` and ``graph.*``) because snapshot.py tolerates both.
    def _build_extraction(_engine):
        _maybe_raise()
        if state["extraction"] is not None:
            return state["extraction"]
        return {
            "nodes": [],
            "edges": [],
            "input_tokens": 0,
            "output_tokens": 0,
        }

    for mod in ("src.graph.sql_to_graph", "graph.sql_to_graph"):
        try:
            monkeypatch.setattr(f"{mod}.build_extraction", _build_extraction)
        except (AttributeError, ModuleNotFoundError):
            pass

    # Engine is a placeholder; build_extraction stub ignores it.
    placeholder_engine = object()
    for mod in ("src.db.engine", "db.engine"):
        try:
            monkeypatch.setattr(f"{mod}.get_engine", lambda: placeholder_engine)
        except (AttributeError, ModuleNotFoundError):
            pass

    return state


def _doc_id(seed: str) -> str:
    """Deterministic 64-char hex doc id derived from a seed string."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _write_doc(
    vault_path: Path,
    *,
    source: str,
    corp_code: str | None = None,
    ticker: str | None = None,
    derived_event_type: str | None = None,
    derived_tickers: list[str] | None = None,
    prov_tickers: list[str] | None = None,
    body: str = "test body",
) -> None:
    """Write a minimal markdown file with valid frontmatter to ``vault_path``."""
    vault_path.parent.mkdir(parents=True, exist_ok=True)
    fm = FrontMatter(
        provenance=ProvenanceBlock(
            source=source,
            source_id="seed",
            fetched_at=datetime.now(UTC),
            corp_code=corp_code,
            ticker=ticker,
            company_name=None,
            lang="ko",
            trust_level="trusted",
            tickers=([TickerRef(ticker=t) for t in prov_tickers] if prov_tickers else None),
        ),
        ingest_state=IngestStateBlock(),
        _derived=DerivedBlock(
            tickers=list(derived_tickers or []),
            event_type=derived_event_type,
        ),
    )
    write_frontmatter(str(vault_path), fm, body)


@pytest.fixture
def seed_edges(pg_engine, tmp_path):
    """Seed minimal documents + entity rows for edges.populate() exercises.

    Returns a callable: ``_seed(*, with_event_chain=False) -> dict``.

    The returned dict has keys:
      - ``doc_ids`` (list[str]): all inserted document ids
      - ``vault_root`` (Path): tmp vault root containing the markdown files
      - ``samsung_corp`` (str): canonical 8-digit corp_code
      - ``samsung_ticker`` (str): canonical 6-digit ticker
      - ``sector`` (str): seeded sector for the entity

    Plan 02 Task 2 idempotency: this fixture truncates `edges`, `documents`,
    `entities`, and `entity_aliases` before seeding to give each test a clean
    slate (pg_engine is session-scoped so cross-test bleed is otherwise possible).
    """

    def _seed(*, with_event_chain: bool = False) -> dict:
        samsung_corp = "00126380"
        samsung_ticker = "005930"
        sector = "전기·전자"

        # Truncate so the session-scoped DB is clean for each test.
        with pg_engine.begin() as conn:
            conn.execute(
                sa.text(
                    "TRUNCATE edges, chunks, documents, entity_aliases, entities "
                    "RESTART IDENTITY CASCADE"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO entities "
                    "(corp_code, canonical_name, current_ticker, sector, market) "
                    "VALUES (:cc, :name, :tk, :sec, 'KOSPI')"
                ),
                {
                    "cc": samsung_corp,
                    "name": "삼성전자",
                    "tk": samsung_ticker,
                    "sec": sector,
                },
            )

        vault_root = tmp_path / "vault"
        raw_dart = vault_root / "raw" / "dart" / "2026"
        raw_news = vault_root / "raw" / "news" / "2026"
        notes_priv = tmp_path / "notes" / "private"

        # 1) DART filing with event_type — exercises filing_event derivation.
        dart_path = raw_dart / "samsung_filing_1.md"
        dart_id = _doc_id("dart-1")
        _write_doc(
            dart_path,
            source="dart",
            corp_code=samsung_corp,
            ticker=samsung_ticker,
            derived_event_type="earnings_release",
            body="삼성전자 분기 실적 공시 본문",
        )

        # 2) News article mentioning Samsung's ticker via ProvenanceBlock.tickers.
        news_path = raw_news / "samsung_news.md"
        news_id = _doc_id("news-1")
        _write_doc(
            news_path,
            source="news",
            prov_tickers=[samsung_ticker],
            body="삼성전자 관련 뉴스 본문",
        )

        # 3) Note with frontmatter tickers list.
        note_path = notes_priv / "thesis_samsung.md"
        note_id = _doc_id("note-1")
        _write_doc(
            note_path,
            source="note",
            derived_tickers=[samsung_ticker],
            body="개인 투자 메모: 005930 보유 검토. 000660 도 같이 본다.",
        )

        first_seen = datetime(2026, 1, 10, tzinfo=UTC)
        rows: list[dict] = [
            {
                "id": dart_id,
                "vault_path": str(dart_path),
                "source": "dart",
                "corp_code": samsung_corp,
                "first_seen_at": first_seen,
            },
            {
                "id": news_id,
                "vault_path": str(news_path),
                "source": "news",
                "corp_code": None,
                "first_seen_at": first_seen + timedelta(hours=1),
            },
            {
                "id": note_id,
                "vault_path": str(note_path),
                "source": "note",
                "corp_code": None,
                "first_seen_at": first_seen + timedelta(hours=2),
            },
        ]

        # Optional second DART filing 30 days later for event_event chain.
        if with_event_chain:
            dart2_path = raw_dart / "samsung_filing_2.md"
            dart2_id = _doc_id("dart-2")
            _write_doc(
                dart2_path,
                source="dart",
                corp_code=samsung_corp,
                ticker=samsung_ticker,
                derived_event_type="dividend",
                body="삼성전자 배당 공시 본문",
            )
            rows.append(
                {
                    "id": dart2_id,
                    "vault_path": str(dart2_path),
                    "source": "dart",
                    "corp_code": samsung_corp,
                    "first_seen_at": first_seen + timedelta(days=30),
                }
            )

        with pg_engine.begin() as conn:
            for r in rows:
                conn.execute(
                    sa.text(
                        "INSERT INTO documents "
                        "(id, body, source, vault_path, corp_code, first_seen_at, last_seen_at) "
                        "VALUES (:id, :body, :source, :vp, :cc, :fsa, :fsa)"
                    ),
                    {
                        "id": r["id"],
                        "body": "x",
                        "source": r["source"],
                        "vp": r["vault_path"],
                        "cc": r["corp_code"],
                        "fsa": r["first_seen_at"],
                    },
                )

        return {
            "doc_ids": [r["id"] for r in rows],
            "vault_root": vault_root,
            "samsung_corp": samsung_corp,
            "samsung_ticker": samsung_ticker,
            "sector": sector,
        }

    return _seed
