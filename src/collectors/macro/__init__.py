"""Macro collector (ECOS + FRED) — Phase 1 v2.0 DB-direct.

Plan 01-03 cutover: writes to ``macro_series`` table via ``db_writer`` instead
of Markdown vault files. ``engine`` is now REQUIRED — passing ``None`` raises
``CollectorConfigError`` at startup before any series runs.

R-05 semantics:
  STARTUP fail-fast: missing engine / missing API key / unreadable catalog →
  ``CollectorConfigError`` before any series runs.
  PER-SERIES soft-fail: ``MacroEmptyResultError`` on one series → caught into
  ``stats['failed']``, sibling series continue (isolation).

R-06 revisions: same ``(source, series_id, item_code, obs_date)`` with a NEW
value is persisted via UPDATE and surfaced through the structured stderr log's
``revisions`` extra (consumed by plan 01-08 into ``collector_runs.extra``).

R-10: catalog path resolves module-relative (repo root / .planning) by
default; ``catalog_path=`` kwarg overrides for tests.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from collectors.macro import client, db_writer, fetcher
from collectors.macro.client import (
    CollectorConfigError,
    MacroEmptyResultError,
    require_env,
)
from shared.run_log import record_collector_run

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_PATH = _REPO_ROOT / ".planning" / "macro_series.yaml"

__all__ = ["collect_macro", "load_catalog"]


def load_catalog(path: Path | None = None) -> dict:
    """Load the macro series catalog. Raises CollectorConfigError on read failure."""
    resolved = path if path is not None else _CATALOG_PATH
    try:
        raw = Path(resolved).read_text(encoding="utf-8")
    except OSError as exc:
        raise CollectorConfigError(f"macro catalog unreadable at {resolved}") from exc
    data = yaml.safe_load(raw) or {}
    return {"ecos": list(data.get("ecos") or []), "fred": list(data.get("fred") or [])}


def collect_macro(
    *,
    engine: Engine | None = None,
    series: list[str] | None = None,
    catalog_path: Path | None = None,
) -> dict[str, Any]:
    """Run ECOS + FRED collection. Returns stats dict.

    Stats shape (v2.0 — RESEARCH Q6):
        {"total": int, "inserted": int, "updated": int, "skipped": int,
         "failed": list[dict], "elapsed_ms": int}

    The legacy ``succeeded`` counter is split into ``inserted`` + ``updated``
    because UPSERT semantics make a single counter misleading.
    """
    if engine is None:
        raise CollectorConfigError("collect_macro requires a DB engine")

    start = time.monotonic()
    catalog = load_catalog(catalog_path)

    entries: list[tuple[str, dict]] = [("ecos", e) for e in catalog["ecos"]] + [
        ("fred", e) for e in catalog["fred"]
    ]
    if series is not None:
        want = set(series)
        entries = [(s, e) for (s, e) in entries if e.get("label") in want]

    # R-05 STARTUP fail-fast: verify every required API key BEFORE any series runs.
    needs_ecos = any(s == "ecos" for s, _ in entries)
    needs_fred = any(s == "fred" for s, _ in entries)
    if needs_ecos:
        require_env("ECOS_API_KEY")
    if needs_fred:
        require_env("FRED_API_KEY")

    stats: dict[str, Any] = {
        "total": len(entries),
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": [],
    }
    all_revisions: list[dict] = []
    ecos_api = None
    fred_api = None

    for source, entry in entries:
        label = entry.get("label", "?")
        try:
            if source == "ecos":
                if ecos_api is None:
                    ecos_api = client.ecos_client()
                obs = fetcher.fetch_ecos_series(
                    ecos_api,
                    entry["series_id"],
                    entry.get("cycle", "D"),
                    entry.get("item_code", ""),
                )
            else:
                if fred_api is None:
                    fred_api = client.fred_client()
                obs = fetcher.fetch_fred_series(fred_api, entry["series_id"])

            inserted, updated, revs = db_writer.upsert_macro_observations(
                engine,
                source=source,
                series_id=entry["series_id"],
                item_code=entry.get("item_code", ""),
                label=label,
                cycle=entry.get("cycle", "D"),
                observations=obs,
            )
            stats["inserted"] += inserted
            stats["updated"] += updated
            if inserted == 0 and updated == 0:
                stats["skipped"] += 1
            for rev in revs:
                all_revisions.append({"series_id": entry["series_id"], **rev})
        except MacroEmptyResultError as exc:
            stats["failed"].append({"doc": label, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001 — per-series isolation (R-05)
            _log.exception("macro collect failed for %s", label)
            stats["failed"].append({"doc": label, "error": str(exc)})

    stats["elapsed_ms"] = int((time.monotonic() - start) * 1000)
    _log.info(
        "collector_run_complete",
        extra={
            "source": "macro",
            "stats": stats,
            "elapsed_ms": stats["elapsed_ms"],
            "revisions": all_revisions if all_revisions else None,
        },
    )
    # Plan 01-08: dual-sink — record_collector_run is the DB row half of the
    # observability contract (RESEARCH.md Q5). Best-effort: a DB outage here
    # logs a WARNING but does NOT fail the collect run.
    run_extra: dict[str, Any] | None = (
        {"revisions": all_revisions} if all_revisions else None
    )
    record_collector_run(
        engine, "macro", stats, stats["elapsed_ms"], extra=run_extra
    )
    return stats
