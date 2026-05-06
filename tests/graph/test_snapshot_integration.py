"""Phase 7.1 SC-1/SC-2 자동 검증: snapshot이 비어있지 않은 graph.json을 만든다.

gap-1 (Phase 7 HUMAN-UAT.md test_id 2): graphifyy AST 경로로는 markdown vault
에서 ``{nodes:[], links:[]}`` 빈 그래프가 생성됐다. 본 테스트는 SQL 기반 경로
로 변경한 뒤 회귀를 막는 자동 가드.

Three guards:

1. ``test_snapshot_produces_non_empty_graph_json``
   seed_edges + edges.populate → snapshot → graph.json에 nodes/links가 모두
   비어있지 않음을 확인 (gap-1 회귀 가드, SC-1).
2. ``test_graph_json_link_carries_tag``
   edges.tag(EXTRACTED/INFERRED)가 graph.json의 link entry까지 보존되는지
   확인 (SC-2).
3. ``test_snapshot_does_not_import_graphify_detect_or_extract``
   graphify.detect / graphify.extract 모듈을 sys.modules에서 차단해도
   snapshot이 ImportError 없이 동작 (SC-4 자동 가드).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


_MIN_CONFIG = {
    "graphify": {
        "raw_windows_days": {},
        "mode": "deep",
        "directed": True,
    }
}


def _scaffold(repo_root: Path) -> None:
    (repo_root / "vault" / "graph").mkdir(parents=True, exist_ok=True)


def _real_build_extraction(engine):
    """Call the on-disk ``build_extraction`` even if a fixture monkeypatched
    a stub onto ``src.graph.sql_to_graph.build_extraction``.

    ``importlib.util.spec_from_file_location`` loads a fresh module instance
    from the source file so we sidestep the patched module in
    ``sys.modules``. Used by integration tests that need real SQL output
    while the same fixture's stub remains active for the snapshot pipeline.
    """
    import importlib.util
    from pathlib import Path

    here = Path(__file__).resolve()
    src_path = here.parents[2] / "src" / "graph" / "sql_to_graph.py"
    spec = importlib.util.spec_from_file_location(
        "_real_sql_to_graph", str(src_path)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_extraction(engine)


def _has_real_graphify() -> bool:
    """Detect a fully-installed graphify (not the test stub).

    The graphify_stub fixture inserts only six submodules; the real package
    additionally exposes ``graphify.detect`` and ``graphify.extract``. We
    check for an attribute the stub never provides so we never accidentally
    treat the stub as the real thing.
    """
    spec = importlib.util.find_spec("graphify.detect")
    return spec is not None


def test_snapshot_produces_non_empty_graph_json(
    tmp_path,
    graphify_stub,
    seed_edges,
    pg_engine,
    monkeypatch,
):
    """Seed real SQL edges, run snapshot, assert graph.json has nodes + links.

    gap-1 regression guard: previously the markdown-AST path returned
    {nodes: [], links: []} on a populated vault. The SQL path materialises
    every endpoint reachable from `edges` so both lists must be non-empty.
    """
    from src.graph.snapshot import snapshot
    from ingest.edges import populate

    _scaffold(tmp_path)

    seeded = seed_edges(with_event_chain=True)
    with pg_engine.begin() as conn:
        populate(seeded["doc_ids"], conn)

    # Inject the real build_extraction output into the stub so the integration
    # path exercises the actual SQL adapter end-to-end.
    graphify_stub["extraction"] = _real_build_extraction(pg_engine)

    out_dir = snapshot(tmp_path, _MIN_CONFIG)
    graph_path = out_dir / "graph.json"
    assert graph_path.exists(), f"graph.json not written to {out_dir}"

    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = payload.get("nodes", [])
    links = payload.get("links", []) or payload.get("edges", [])
    assert nodes, "Phase 7.1 gap-1 regression: graph.json has no nodes"
    assert links, "Phase 7.1 gap-1 regression: graph.json has no links"

    # GRAPH_REPORT.md and index.html must also exist (contract preserved).
    assert (out_dir / "GRAPH_REPORT.md").exists()
    assert (out_dir / "index.html").exists()


def test_graph_json_link_carries_tag(tmp_path, graphify_stub):
    """edges.tag (EXTRACTED/INFERRED) round-trips into graph.json links."""
    from src.graph.snapshot import snapshot

    _scaffold(tmp_path)
    graphify_stub["extraction"] = {
        "nodes": [
            {
                "id": "doc1",
                "type": "document",
                "label": "d1",
                "source_file": "vault/raw/dart/x.md",
            },
            {
                "id": "005930",
                "type": "ticker",
                "label": "삼성전자",
                "source_file": "db://entities/005930",
            },
        ],
        "edges": [
            {
                "source": "doc1",
                "target": "005930",
                "edge_type": "mentions_ticker",
                "tag": "EXTRACTED",
                "weight": 1.0,
            },
        ],
        "input_tokens": 0,
        "output_tokens": 0,
    }

    out_dir = snapshot(tmp_path, _MIN_CONFIG)
    payload = json.loads((out_dir / "graph.json").read_text(encoding="utf-8"))
    links = payload.get("links", []) or payload.get("edges", [])
    assert links, "no links written to graph.json"
    assert any(L.get("tag") in {"EXTRACTED", "INFERRED"} for L in links), (
        f"edges.tag did not survive into graph.json: {links}"
    )


def test_snapshot_does_not_import_graphify_detect_or_extract(
    tmp_path,
    graphify_stub,
    monkeypatch,
):
    """SC-4 guard: snapshot path is graphify.detect/extract-free.

    Inserts ``None`` into sys.modules for both names so any residual
    ``from graphify.detect import ...`` would raise ImportError immediately.
    """
    from src.graph.snapshot import snapshot

    _scaffold(tmp_path)
    for name in ("graphify.detect", "graphify.extract"):
        monkeypatch.setitem(sys.modules, name, None)

    graphify_stub["extraction"] = {
        "nodes": [
            {
                "id": "n1",
                "type": "ticker",
                "label": "X",
                "source_file": "db://entities/n1",
            }
        ],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    # Should not raise — proves the new path never imports detect/extract.
    out_dir = snapshot(tmp_path, _MIN_CONFIG)
    assert (out_dir / "graph.json").exists()


@pytest.mark.skipif(
    not _has_real_graphify(),
    reason="real graphify package not installed; stub-only round-trip is "
    "covered by the other tests",
)
def test_snapshot_with_real_graphify_round_trip(
    tmp_path,
    seed_edges,
    pg_engine,
    monkeypatch,
):
    """End-to-end round-trip with the actual graphify library (no stub).

    Exercises ``snapshot`` against the full graphify build/cluster/export
    pipeline so contract drift in graphifyy 0.7.x is caught locally rather
    than at CLI run time. Skipped automatically when graphify is not on the
    test interpreter (e.g., minimal CI guard envs).
    """
    from src.graph.snapshot import snapshot
    from ingest.edges import populate

    _scaffold(tmp_path)
    seeded = seed_edges(with_event_chain=True)
    with pg_engine.begin() as conn:
        populate(seeded["doc_ids"], conn)

    # Patch get_engine so snapshot uses the test engine, not the live one.
    monkeypatch.setattr("src.db.engine.get_engine", lambda: pg_engine)

    out_dir = snapshot(tmp_path, _MIN_CONFIG)
    payload = json.loads((out_dir / "graph.json").read_text(encoding="utf-8"))
    nodes = payload.get("nodes", [])
    links = payload.get("links", []) or payload.get("edges", [])
    assert nodes, "real graphify produced empty nodes (gap-1 still alive!)"
    assert links, "real graphify produced empty links"
