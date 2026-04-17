"""Ingest rebuild from vault — STORE-05 / D-25/26/27/28/29.

Full wipe + rebuild strategy:
  1. snapshot current DB (counts + distinct embedding_models)
  2. if dry_run: print the plan, return without touching anything
  3. if TTY and not assume_yes: prompt "y/N"; abort on anything other than "y"
  4. ``alembic downgrade base`` -> wipes every Phase-2/3 table and extension rows
  5. ``alembic upgrade head`` -> recreates schema
  6. ``ingest_run(vault_root, engine, force_reembed=True)`` -> re-ingest everything
  7. snapshot again; return {wiped, rebuilt, ingest_stats}

D-29 idempotence guarantee: running ``ingest_run`` then ``rebuild_from_vault``
on the same vault yields the same set of documents.id values (content-hash
primary key) and same chunk counts per document. Embedding float values may
vary within tolerance (bge-m3 is CPU-deterministic but halving/quantization
could drift in future — equality of the embedding column is not promised).

Incremental reconcile is Phase 9's ``ingest doctor`` job, not this module.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

from ingest.embedder import EMBEDDING_MODEL_VERSION
from ingest.worker import ingest_run

__all__ = ["rebuild_from_vault", "snapshot_db"]


_ALEMBIC_INI = "src/db/alembic.ini"


def snapshot_db(engine: Engine) -> dict[str, Any]:
    """Count documents + chunks + list distinct embedding models.

    Returns {} if the tables don't exist yet (e.g. mid-downgrade).
    """
    try:
        with engine.connect() as conn:
            docs = conn.execute(sa.text("SELECT count(*) FROM documents")).scalar_one()
            chunks = conn.execute(sa.text("SELECT count(*) FROM chunks")).scalar_one()
            models = sorted(
                r[0]
                for r in conn.execute(sa.text("SELECT DISTINCT embedding_model FROM chunks"))
                if r[0] is not None
            )
        return {
            "documents": int(docs),
            "chunks": int(chunks),
            "distinct_embedding_models": models,
        }
    except Exception:  # noqa: BLE001 — tables may not exist
        return {"documents": 0, "chunks": 0, "distinct_embedding_models": []}


def _alembic_config(engine: Engine) -> Config:
    """Build an Alembic Config bound to the caller's engine URL.

    We pass the URL explicitly so ``env.py`` does not re-read ``DATABASE_URL``
    if the caller built their engine from a different source (e.g., a
    testcontainer)."""
    cfg = Config(_ALEMBIC_INI)
    # engine.url.__str__ masks the password as '***'. Use render_as_string so
    # alembic actually connects with the real credentials.
    cfg.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))
    return cfg


def rebuild_from_vault(
    vault_root: Path,
    engine: Engine,
    *,
    force_reembed: bool = False,
    dry_run: bool = False,
    assume_yes: bool = False,
) -> dict[str, Any]:
    """Wipe the DB via alembic downgrade base + upgrade head, then re-ingest.

    Parameters
    ----------
    vault_root
        Vault root directory (contains ``raw/`` + ``ingested/``).
    engine
        SQLAlchemy Engine pointing at the target DB.
    force_reembed
        Passed through to ``ingest_run`` — rebuild already force-reembeds by
        construction (empty chunks table after wipe) but this preserves the
        flag for operational symmetry.
    dry_run
        If True: print the plan, return ``{"dry_run": True, ...}`` without
        touching the DB or prompting.
    assume_yes
        Skip the interactive TTY prompt (D-28). CI/cron should always pass
        ``--yes``.

    Returns
    -------
    dict
        ``{"dry_run": True, ...}`` when dry-run;
        ``{"aborted": True}`` when the user declined;
        otherwise ``{"wiped": {...}, "rebuilt": {...}, "ingest_stats": {...}}``.
    """
    before = snapshot_db(engine)
    raw_root = vault_root / "raw"
    vault_files = sorted(raw_root.rglob("*.md")) if raw_root.exists() else []
    n_files = len(vault_files)

    plan = {
        "would_wipe": before,
        "would_process_files": n_files,
        "embedding_model": EMBEDDING_MODEL_VERSION,
    }

    if dry_run:
        print(f"Would wipe: {before['documents']} documents, {before['chunks']} chunks")
        print(f"Would process: {n_files} vault files")
        print(f"Embedding model: {EMBEDDING_MODEL_VERSION}")
        return {"dry_run": True, **plan}

    # D-28: TTY prompt unless --yes.
    if not assume_yes and sys.stdin.isatty():
        prompt = (
            f"This will wipe the DB ({before['documents']} documents, "
            f"{before['chunks']} chunks) and reprocess {n_files} vault files. "
            "Continue? [y/N]: "
        )
        try:
            response = input(prompt).strip().lower()
        except EOFError:
            response = ""
        if response != "y":
            return {"aborted": True, **plan}

    # D-25: alembic round-trip (downgrade base -> upgrade head).
    cfg = _alembic_config(engine)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    # Re-ingest. force_reembed is moot post-wipe (empty chunks table) but
    # we pass True explicitly so the predicate is unambiguous.
    _ = force_reembed  # operational symmetry with ingest_run; semantically True here
    ingest_stats = ingest_run(vault_root, engine, force_reembed=True)

    after = snapshot_db(engine)
    return {
        "wiped": before,
        "rebuilt": after,
        "ingest_stats": ingest_stats,
    }
