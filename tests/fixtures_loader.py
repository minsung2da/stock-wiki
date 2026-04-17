"""YAML fixture loader for Phase 2 entity tests.

All INSERTs use SQLAlchemy `text()` with bind parameters — fixture YAML is
trusted test data (committed to repo), but the defensive parameterized pattern
prevents a poisoned fixture from executing arbitrary SQL (threat T-02-12).
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
import yaml
from sqlalchemy.engine import Engine


def load_entity_fixture(engine: Engine, fixture_path: str | Path) -> None:
    """Load a YAML fixture into entities/entity_aliases/documents/edges."""
    data = yaml.safe_load(Path(fixture_path).read_text(encoding="utf-8"))
    with engine.begin() as conn:
        for e in data.get("entities", []) or []:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO entities (
                        corp_code, canonical_name, current_ticker,
                        market, listed_at, delisted_at
                    )
                    VALUES (
                        :corp_code, :canonical_name, :current_ticker,
                        :market, :listed_at, :delisted_at
                    )
                    """
                ),
                {
                    "corp_code": e["corp_code"],
                    "canonical_name": e["canonical_name"],
                    "current_ticker": e.get("current_ticker"),
                    "market": e.get("market"),
                    "listed_at": e.get("listed_at"),
                    "delisted_at": e.get("delisted_at"),
                },
            )
        for a in data.get("entity_aliases", []) or []:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO entity_aliases
                      (corp_code, kind, value, valid_from, valid_to)
                    VALUES
                      (:corp_code, :kind, :value, :valid_from, :valid_to)
                    """
                ),
                a,
            )
        for d in data.get("documents", []) or []:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO documents (id, body, source, vault_path)
                    VALUES (:id, :body, :source, :vault_path)
                    """
                ),
                d,
            )
        for edge in data.get("edges", []) or []:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO edges
                      (src_type, src_id, dst_type, dst_id, edge_type)
                    VALUES
                      (:src_type, :src_id, :dst_type, :dst_id, :edge_type)
                    """
                ),
                edge,
            )
