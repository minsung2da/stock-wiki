"""DART collector — A+B filings only (D-01), no LLM, no DB (COLL-06).

Writes minimal-frontmatter Markdown to `vault/raw/dart/YYYY/{rcept_no}_{corp_code}.md`
with content-hash idempotency (COLL-08) and per-filing error isolation. Updates
`vault/ingested/_status/heartbeat.md` atomically after the run (COLL-09).

NO imports of `anthropic` or `openai` — guarded by tests/test_import_guard.py
(COLL-07 CI discipline).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from collectors.dart import client, fetcher, writer
from ingest.heartbeat import record_source_run

__all__ = ["collect_dart"]


def collect_dart(
    corp_code: str,
    since: str,
    max_docs: int = 100,
    vault_root: Path = Path("vault"),
) -> dict[str, Any]:
    """Collect DART A+B filings for a single corp into `vault/raw/dart/YYYY/`.

    Parameters
    ----------
    corp_code : str
        8-digit DART corporation code (e.g., "00126380" for Samsung Electronics).
    since : str
        ISO date "YYYY-MM-DD" — earliest filing receipt date to include.
    max_docs : int
        Phase-3 cap (D-03). Phase 4 removes this.
    vault_root : Path
        Root of the Obsidian vault. Defaults to "vault" relative to cwd.

    Returns
    -------
    dict
        {"total": int, "succeeded": int, "skipped": int, "failed": list[dict]}
        Heartbeat is updated with the same stats.
    """
    client.get_client()
    corp = client.find_corp(corp_code)
    ticker = getattr(corp, "stock_code", None)

    filings = fetcher.list_ab_filings(corp_code, since, max_docs)

    stats: dict[str, Any] = {
        "total": len(filings),
        "succeeded": 0,
        "skipped": 0,
        "failed": [],
    }

    for filing in filings:
        path = writer.vault_path_for(filing, corp_code, vault_root)
        try:
            # Fetch body up-front so the content-hash comparison reflects
            # the current remote state (COLL-08: dedup on content, not URL).
            body = fetcher.fetch_body(filing)
            new_hash = writer.compute_body_hash(body)

            if path.exists():
                existing_hash = _read_existing_hash(path)
                if existing_hash == new_hash:
                    stats["skipped"] += 1
                    continue

            writer.write_filing(filing, body, corp_code, ticker, vault_root)
            stats["succeeded"] += 1
        except Exception as exc:  # per-filing isolation (COLL-08)
            stats["failed"].append({"doc": str(path), "error": str(exc)})

    record_source_run(
        "dart",
        stats,
        heartbeat_path=vault_root / "ingested/_status/heartbeat.md",
    )
    return stats


def _read_existing_hash(path: Path) -> str | None:
    """Read the content_hash recorded in an existing vault file's frontmatter.

    Returns None if the file has no frontmatter content_hash field. The
    collector then treats the file as "unknown state" and re-writes it.
    """
    from shared.frontmatter import read_frontmatter

    try:
        fm, _ = read_frontmatter(str(path))
    except Exception:
        return None
    return fm.provenance.content_hash
