"""Macro collector (ECOS + FRED) — COLL-04.

PHASE 1 TRANSITION (v2.0): this collector still writes via writer.py but no
longer receives ``vault_root`` via CLI. ``_LEGACY_VAULT_ROOT`` will be
removed when ``db_writer.*`` replaces ``writer.*`` in plan 01-03.

R-05 semantics:
  STARTUP fail-fast: missing API key / unreadable catalog → CollectorConfigError
  before any series runs.
  PER-SERIES soft-fail: MacroEmptyResultError on one series → caught into
  stats['failed'], sibling series continue (isolation).

R-06 revisions: same-date different-value observations are persisted with the
new value and the change is surfaced to heartbeat via `extra={'revisions': [...]}`.

R-10: catalog path resolves module-relative (repo root / .planning) by
default; `catalog_path=` kwarg overrides for tests.

R-12: `engine` kwarg is unused here — macro docs have no entity resolution
requirement. Kept for signature parity with collect_krx / collect_news /
collect_kind so the orchestrator can call collectors uniformly.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from collectors.macro import client, fetcher, writer
from collectors.macro.client import (
    CollectorConfigError,
    MacroEmptyResultError,
    require_env,
)
from shared.heartbeat import record_source_run

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_PATH = _REPO_ROOT / ".planning" / "macro_series.yaml"
_ECOS_URL = "https://ecos.bok.or.kr/"
_FRED_URL = "https://fred.stlouisfed.org/series/"

# Phase 1 transition placeholder; removed in 01-03 (macro DB-direct cutover).
_LEGACY_VAULT_ROOT = Path("vault")

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
    engine: Engine | None = None,  # noqa: ARG001 — R-12 signature parity
    series: list[str] | None = None,
    catalog_path: Path | None = None,
) -> dict[str, Any]:
    """Run ECOS + FRED collection. Returns stats dict."""
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
        "succeeded": 0,
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
                url = _ECOS_URL
            else:
                if fred_api is None:
                    fred_api = client.fred_client()
                obs = fetcher.fetch_fred_series(fred_api, entry["series_id"])
                url = _FRED_URL + entry["series_id"]

            _, _, rewrote, revs = writer.write_macro_doc(
                vault_root=_LEGACY_VAULT_ROOT,
                source=source,
                series_id=entry["series_id"],
                label=label,
                observations=obs,
                source_url=url,
            )
            for rev in revs:
                all_revisions.append({"series_id": entry["series_id"], **rev})
            if rewrote:
                stats["succeeded"] += 1
            else:
                stats["skipped"] += 1
        except MacroEmptyResultError as exc:
            stats["failed"].append({"doc": label, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001 — per-series isolation (R-05)
            _log.exception("macro collect failed for %s", label)
            stats["failed"].append({"doc": label, "error": str(exc)})

    stats["elapsed_ms"] = int((time.monotonic() - start) * 1000)
    extra: dict | None = {"revisions": all_revisions} if all_revisions else None
    record_source_run(
        "macro",
        stats,
        heartbeat_path=_LEGACY_VAULT_ROOT / "ingested/_status/heartbeat.md",
        extra=extra,
    )
    return stats
