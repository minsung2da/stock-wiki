"""Phase 7.1 GRAPH-01/02: SQL → graphify build_from_json adapter.

Reads the live ``edges`` + ``entities`` + ``documents`` tables (populated by
Phase 2/3/7 collectors + ``src/ingest/edges.py`` post-pass) and emits a
``{"nodes": [...], "edges": [...], "input_tokens": 0, "output_tokens": 0}``
extraction dict that ``graphify.build.build_from_json(extraction,
directed=True)`` consumes verbatim.

NO LLM calls. NO graphify.detect / graphify.extract / graphify.collect_files
calls — gap-1 (Phase 7 UAT) confirmed those return empty for a markdown vault.
This adapter bypasses the LLM extraction layer entirely; the SQL edge taxonomy
locked in Phase 7 (mentions_ticker, note_ticker, ticker_sector, supersedes,
filing_event, event_event) IS the canonical extraction.

graphify v0.7.5 input contract (verified by inspecting
``graphify.build.build_from_json``):

    extraction = {
        "nodes": [
            {"id": str, "type": str, "label": str, "source_file": str, ...},
            ...,
        ],
        "edges": [
            {"source": <node id>, "target": <node id>,
             "edge_type": str, "tag": "EXTRACTED"|"INFERRED",
             "weight": float, ...},
            ...,
        ],
        "input_tokens": 0,
        "output_tokens": 0,
    }

Notes on the contract:
  - Node ``source_file`` is the canonical provenance key. The legacy alias
    ``source`` is auto-renamed by graphify with a stderr warning — we always
    emit ``source_file`` to silence it.
  - Edges use ``source``/``target`` (or ``from``/``to``) — NOT ``src``/``dst``.
    Endpoints not present in ``nodes`` are silently dropped by graphify, so
    we materialise every endpoint reachable from edges as a node.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

__all__ = ["build_extraction"]


def _node_label_and_source(
    ntype: str,
    nid: str,
    *,
    doc_meta: dict[str, dict[str, str]],
    entity_by_ticker: dict[str, str],
) -> tuple[str, str]:
    """Return (label, source_file) for a node based on its type and id.

    Pure function — no DB IO; callers pre-load metadata maps.
    """
    if ntype == "document":
        meta = doc_meta.get(nid, {})
        vault_path = meta.get("vault_path", "")
        if vault_path:
            return Path(vault_path).stem, vault_path
        return nid[:12], f"db://documents/{nid}"
    if ntype == "ticker":
        return entity_by_ticker.get(nid, nid), f"db://entities/{nid}"
    if ntype == "sector":
        return nid, f"db://sectors/{nid}"
    if ntype == "event":
        return nid, f"db://events/{nid}"
    return nid, f"db://{ntype}/{nid}"


def build_extraction(engine: Engine) -> dict[str, Any]:
    """SQL → graphify build_from_json compatible extraction dict.

    Reads ``documents``, ``entities``, and ``edges`` once each (3 queries
    total — corpus-wide; not chunked because graphify needs the full graph
    to compute centrality). Materialises every endpoint reachable from
    ``edges`` as a node. ``tag`` and ``edge_type`` columns survive as edge
    attributes.

    Returns
    -------
    dict
        ``{"nodes": [...], "edges": [...], "input_tokens": 0,
        "output_tokens": 0}`` — empty lists when the DB is empty.
    """
    with engine.connect() as conn:
        ent_rows = (
            conn.execute(
                sa.text(
                    "SELECT corp_code, canonical_name, current_ticker, sector "
                    "FROM entities"
                )
            )
            .mappings()
            .all()
        )
        doc_rows = (
            conn.execute(
                sa.text("SELECT id, vault_path, source FROM documents")
            )
            .mappings()
            .all()
        )
        edge_rows = (
            conn.execute(
                sa.text(
                    "SELECT src_type, src_id, dst_type, dst_id, edge_type, tag "
                    "FROM edges"
                )
            )
            .mappings()
            .all()
        )

    entity_by_ticker: dict[str, str] = {
        r["current_ticker"]: r["canonical_name"]
        for r in ent_rows
        if r["current_ticker"]
    }
    doc_meta: dict[str, dict[str, str]] = {
        r["id"]: {"vault_path": r["vault_path"], "source": r["source"]}
        for r in doc_rows
    }

    nodes_by_id: dict[str, dict[str, Any]] = {}

    def _ensure_node(ntype: str, nid: str) -> None:
        if nid in nodes_by_id:
            return
        label, source_file = _node_label_and_source(
            ntype,
            nid,
            doc_meta=doc_meta,
            entity_by_ticker=entity_by_ticker,
        )
        nodes_by_id[nid] = {
            "id": nid,
            "type": ntype,
            "label": label,
            "source_file": source_file,
        }

    edges_out: list[dict[str, Any]] = []
    for r in edge_rows:
        _ensure_node(r["src_type"], r["src_id"])
        _ensure_node(r["dst_type"], r["dst_id"])
        edges_out.append(
            {
                "source": r["src_id"],
                "target": r["dst_id"],
                "edge_type": r["edge_type"],
                "tag": r["tag"],
                "weight": 1.0,
            }
        )

    return {
        "nodes": list(nodes_by_id.values()),
        "edges": edges_out,
        "input_tokens": 0,
        "output_tokens": 0,
    }
