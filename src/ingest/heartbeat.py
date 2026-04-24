"""Heartbeat atomic writer (D-15, COLL-09, Pattern 8).

Records per-source ingest/collection activity into
`vault/ingested/_status/heartbeat.md` so dashboards and `ingest doctor`
can detect stale sources. The file has a Markdown body with a top-level
YAML `sources` dict that is outside the FrontMatter Pydantic schema
(schema covers only trusted/semi_trusted/adversarial document frontmatter;
heartbeat is operational telemetry).

Pitfall 6: atomic write. tempfile + os.replace in the SAME directory —
POSIX atomic, best-effort on Windows. On failure the original file is
preserved and no `.tmp` files are left behind.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

HEARTBEAT_PATH_DEFAULT = Path("vault/ingested/_status/heartbeat.md")
HEARTBEAT_BODY = "<!-- auto-generated; do not edit -->\n"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _read_sources(path: Path) -> dict[str, Any]:
    """Read existing heartbeat metadata; return empty dict if missing.

    Heartbeat file is YAML-frontmatter-only markdown. Parsed via yaml.safe_load
    directly because the `sources` key lives at the top level of frontmatter,
    outside the FrontMatter Pydantic schema.
    """
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    raw_yaml = text[3:end]
    data = yaml.safe_load(raw_yaml) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _atomic_write(path: Path, content: str) -> None:
    """Write content atomically via tempfile + os.replace in same directory.

    Mirrors the pattern from src/shared/frontmatter.write_frontmatter. If
    os.replace raises, the temp file is removed and the original file
    (if any) is untouched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, str(path))
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


_RESERVED_SOURCE_KEYS = frozenset({"last_run", "last_success", "last_failure", "docs_processed"})


def record_source_run(
    source: str,
    stats: dict[str, Any],
    heartbeat_path: Path | None = None,
    *,
    extra: dict | None = None,
) -> None:
    """Update heartbeat.md with the outcome of a single source's run.

    `stats` shape: {"total": int, "succeeded": int, "skipped": int, "failed": list|int}.
    Preserves prior `last_success` when current run has failures, and vice versa.
    `last_run` and `docs_processed` (= stats.succeeded) are always updated.

    `extra` (optional kwarg, Phase 4): a dict of non-secret flags merged into the
    per-source block alongside stats-derived keys. Reserved keys (last_run,
    last_success, last_failure, docs_processed) cannot be overridden — they are
    silently dropped from `extra` (T-04-22 defense-in-depth).

    Other source blocks are preserved verbatim (per-source isolation, COLL-08).
    """
    path = heartbeat_path if heartbeat_path is not None else HEARTBEAT_PATH_DEFAULT
    meta = _read_sources(path)
    sources = meta.get("sources")
    if not isinstance(sources, dict):
        sources = {}

    prev = sources.get(source)
    if not isinstance(prev, dict):
        prev = {}

    now = _now_iso()
    failed = stats.get("failed") or []
    had_failure = bool(failed) if not isinstance(failed, int) else failed > 0

    new_block: dict[str, Any] = {
        "last_run": now,
        "docs_processed": int(stats.get("succeeded", 0)),
    }
    if had_failure:
        new_block["last_failure"] = now
        if "last_success" in prev:
            new_block["last_success"] = prev["last_success"]
    else:
        new_block["last_success"] = now
        if "last_failure" in prev:
            new_block["last_failure"] = prev["last_failure"]

    if extra:
        for k, v in extra.items():
            if k not in _RESERVED_SOURCE_KEYS:
                new_block[k] = v

    # Phase 5: auto-populate alert_level for 'enrich' source if caller didn't
    if source == "enrich" and "alert_level" not in new_block:
        new_block["alert_level"] = compute_enrich_alert_level(
            extra=new_block,  # new_block already has the extra fields merged
            prior_block=prev,
            now_iso=now,
        )

    sources[source] = new_block
    meta["sources"] = sources

    yaml_text = yaml.safe_dump(meta, sort_keys=True, allow_unicode=True)
    content = f"---\n{yaml_text}---\n{HEARTBEAT_BODY}"
    _atomic_write(path, content)


# === Phase 5 additions ===


def compute_enrich_alert_level(
    extra: dict[str, Any] | None,
    prior_block: dict[str, Any] | None,
    now_iso: str | None = None,
) -> str | None:
    """D-24 SLA thresholds for the enrich source.

    Thresholds (any triggers -> 'warn' unless specified):
      - consecutive_failures >= 2        -> 'warn'
      - backlog_count > 50               -> 'warn'
      - now - last_run > 26h             -> 'warn'
      - review_flagged ratio > 10%       -> 'info'
    'warn' overrides 'info'. Returns None if all thresholds clear.
    """
    level: str | None = None
    extra = extra or {}
    cf = int(extra.get("consecutive_failures", 0))
    backlog = int(extra.get("backlog_count", 0))
    processed = int(extra.get("docs_processed", 0))
    flagged = int(extra.get("docs_review_flagged", 0))

    if processed > 0 and (flagged / processed) > 0.10:
        level = "info"
    if cf >= 2:
        level = "warn"
    if backlog > 50:
        level = "warn"

    # stale last_run check (26h)
    if prior_block and now_iso:
        last_run = prior_block.get("last_run")
        if isinstance(last_run, str):
            try:
                lr = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
                if (now - lr).total_seconds() > 26 * 3600:
                    level = "warn"
            except (ValueError, TypeError):
                pass
    return level


def write_disk_section(
    disk: dict[str, Any],
    heartbeat_path: Path | None = None,
) -> None:
    """Atomically merge the D-23 top-level `disk` dict into heartbeat.md.

    Preserves `sources` and any other top-level keys verbatim.
    """
    path = heartbeat_path if heartbeat_path is not None else HEARTBEAT_PATH_DEFAULT
    meta = _read_sources(path)
    meta["disk"] = dict(disk)  # shallow copy
    yaml_text = yaml.safe_dump(meta, sort_keys=True, allow_unicode=True)
    content = f"---\n{yaml_text}---\n{HEARTBEAT_BODY}"
    _atomic_write(path, content)
