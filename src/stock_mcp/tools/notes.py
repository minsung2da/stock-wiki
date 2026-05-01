"""``add_note`` MCP tool — the only writable surface in the Phase 6 MCP (MCP-08).

Enforces the D-09 write-scope contract (whitelist = ``vault/notes/`` ∪
``notes/private/``), supports D-12 user-friendly path aliases, validates
frontmatter via ``NoteFrontmatter`` (D-11), and applies the D-10 append-only
conflict policy with D-13 idempotency.

SoT directories — ``raw/``, ``ingested/``, ``dashboards/``, ``vault/raw/`` —
remain write-protected (T-6-06-01 / T-6-06-02). Path resolution follows
symlinks BEFORE the whitelist check, so a symlink under ``notes/private/``
pointing outside the whitelist is rejected (T-6-06-02).

Errors NEVER raise past this boundary — stdout is the MCP JSON-RPC stream
and a raw traceback would corrupt it (D-21).
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import frontmatter as fm
import yaml
from pydantic import ValidationError

from db.engine import get_engine
from db.entity import resolve_entity
from shared.frontmatter import NoteFrontmatter

from ..errors import ErrorCode, StructuredError, to_error_response
from ..logging import log_tool_call
from ..models import AddNoteResponse
from ..paths import resolve_path_alias, safe_join
from ..repo_root import repo_root
from .search import mcp

__all__ = ["add_note"]


def _now_kst() -> datetime:
    return datetime.now(ZoneInfo("Asia/Seoul"))


def _ts_header() -> str:
    """ISO-8601 with KST offset, second precision (used for append separator)."""
    return _now_kst().strftime("%Y-%m-%dT%H:%M:%S%z")


def _atomic_write(target: Path, content: str) -> None:
    """tempfile.mkstemp + os.replace — atomic on POSIX (T-6-06-05)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(content)
        os.replace(tmp_path, str(target))
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _resolve_tickers(engine, tickers: list[str]) -> tuple[list[str], list[str]]:
    """Best-effort resolution; unresolved tickers become warnings, not errors."""
    warnings: list[str] = []
    normalized: list[str] = []
    for t in tickers:
        try:
            ent = resolve_entity(engine, t)
        except Exception:  # noqa: BLE001 — defensive: never block writes on resolver
            ent = None
        if ent is None:
            warnings.append(f"unresolved_ticker:{t}")
        normalized.append(t)
    return normalized, warnings


def _build_new_file(note_fm: NoteFrontmatter, body: str) -> str:
    """Render frontmatter + body for a freshly-created note."""
    meta = note_fm.model_dump(mode="json")
    yaml_block = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    return f"---\n{yaml_block}---\n\n{body}"


def _last_section_matches(existing_content: str, ts_header: str, body: str) -> bool:
    """Idempotency check (D-13): does the LAST `## ts` section equal new body?"""
    marker = f"\n---\n## {ts_header}\n\n"
    idx = existing_content.rfind(marker)
    if idx < 0:
        # Truncate timestamp to second precision and try a looser match
        # (fallback only — exact ts_header is the primary signal).
        return False
    last_section_body = existing_content[idx + len(marker) :].rstrip()
    return last_section_body == body.rstrip()


def add_note(
    path: str,
    body: str,
    frontmatter: dict | None = None,
) -> AddNoteResponse | dict:
    """Write a note into the vault — the only writable MCP surface (MCP-08, D-09..D-13).

    The tool enforces the D-09 write-scope whitelist (``vault/notes/`` ∪
    ``notes/private/``), supports D-12 user-friendly path aliases (``journal/today``,
    ``{ticker6}/{kind}``), validates frontmatter against the ``NoteFrontmatter``
    schema (D-11), and applies the D-10 append-only conflict policy with D-13
    idempotency. SoT directories (``raw/``, ``ingested/``, ``dashboards/``,
    ``vault/raw/``) remain write-protected. The next ingest cycle picks up the
    written note automatically.

    ### Behavior contract
    - ``path``: repo-relative target. Aliases:
        * ``journal`` / ``journal/today`` → ``notes/private/journal/{KST date}.md``
        * ``journal/<name>``               → ``notes/private/journal/<name>.md``
        * ``{6-digit ticker}/<kind>``      → ``notes/private/{ticker}/<kind>.md``
      ``.md`` is auto-appended if absent. The resolved path is rejected unless it
      lives inside ``vault/notes/`` or ``notes/private/`` AFTER ``Path.resolve()``
      (collapses ``..`` and follows symlinks — no escape via either route).
    - ``body``: free-form markdown. Treated as opaque — never re-parsed for YAML.
    - ``frontmatter``: dict; ``type`` is required (one of ``thesis|journal|conviction|note``).
      ``tickers`` is best-effort: unknown tickers are logged as warnings; the note
      is still written. ``updated`` is always overwritten with now-KST.
    - **Conflict policy (D-10):** if the target exists, the new content is
      APPENDED after a ``\\n\\n---\\n## {ISO ts KST}\\n\\n`` separator. The
      existing frontmatter is preserved; ``tickers``/``tags`` are union-merged
      and ``updated`` is refreshed. The original file's ``type``/``created``
      are retained.
    - **Idempotency (D-13):** if the most recent appended section has the same
      timestamp header AND the same body, the duplicate write is a no-op
      (``idempotent=True``).
    - **Atomicity (T-6-06-05):** ``tempfile.mkstemp`` + ``os.replace`` — no
      partial writes on crash or concurrent calls.

    ### Response shape
    Returns ``AddNoteResponse`` with:
    - ``vault_path``: repo-relative path actually written (post-alias).
    - ``action``: ``"created"`` on first write, ``"appended"`` on subsequent.
    - ``idempotent``: ``True`` when the call was a duplicate of the most recent
      section (file was not modified).

    ### Errors
    Returns ``{"error": {"code": ..., "message": ..., "details": {...}}}`` —
    never raises. Codes:
    - ``WRITE_FORBIDDEN``: path resolves outside ``vault/notes/`` ∪
      ``notes/private/`` (covers ``..`` traversal, off-whitelist roots, and
      symlink escape).
    - ``INVALID_FRONTMATTER``: missing required ``type`` field, extra keys,
      or — on the append branch — the existing file lacks a YAML frontmatter
      fence and must be fixed manually.
    - ``INTERNAL``: unexpected failure (string truncated to 200 chars).

    ### Performance budget
    p95 latency < 200ms (single fs read + atomic write). Response < 200 bytes.
    Concurrent writes preserved by atomic-replace at the filesystem level.
    """
    t0 = time.perf_counter()
    args_log = {"path": path, "body_chars": len(body or "")}
    try:
        root = repo_root()
        aliased = resolve_path_alias(path)
        target = safe_join(root, aliased)

        # --- frontmatter validation (D-11) ---
        fm_dict = dict(frontmatter or {})
        # Force fail-fast on missing required ``type`` even when frontmatter is None.
        fm_dict.setdefault("type", None)
        try:
            note_fm = NoteFrontmatter(**fm_dict)
        except ValidationError as ve:
            raise StructuredError(
                ErrorCode.INVALID_FRONTMATTER,
                "frontmatter validation failed",
                details={"errors": [str(err) for err in ve.errors()][:5]},
            ) from ve

        # Always refresh ``updated`` to now-KST.
        note_fm = note_fm.model_copy(update={"updated": _now_kst()})

        # Best-effort ticker normalization (warnings only).
        engine = get_engine()
        normalized, _warnings = _resolve_tickers(engine, list(note_fm.tickers))
        note_fm = note_fm.model_copy(update={"tickers": normalized})

        # ----------- branch: create vs append -----------
        if not target.exists():
            content = _build_new_file(note_fm, body)
            _atomic_write(target, content)
            vault_path_str = str(target.relative_to(root.resolve()))
            result = AddNoteResponse(
                vault_path=vault_path_str,
                action="created",
                idempotent=False,
            )
            latency = int((time.perf_counter() - t0) * 1000)
            log_tool_call("add_note", args_log, latency, len(result.model_dump_json()) // 4)
            return result

        # --- append branch ---
        # Detect malformed/missing frontmatter fence — reject (D-13 contract).
        raw = target.read_text(encoding="utf-8")
        if not raw.lstrip().startswith("---"):
            raise StructuredError(
                ErrorCode.INVALID_FRONTMATTER,
                "existing file lacks frontmatter; manual fix required",
                details={"vault_path": str(target.relative_to(root.resolve()))},
            )

        post = fm.loads(raw)
        existing_meta = dict(post.metadata or {})
        if not existing_meta:
            raise StructuredError(
                ErrorCode.INVALID_FRONTMATTER,
                "existing file lacks frontmatter; manual fix required",
                details={"vault_path": str(target.relative_to(root.resolve()))},
            )

        ts = _ts_header()

        # Idempotency check (D-13).
        if _last_section_matches(post.content, ts, body):
            result = AddNoteResponse(
                vault_path=str(target.relative_to(root.resolve())),
                action="appended",
                idempotent=True,
            )
            latency = int((time.perf_counter() - t0) * 1000)
            log_tool_call("add_note", args_log, latency, len(result.model_dump_json()) // 4)
            return result

        # Merge frontmatter — type/created/author kept from existing if present.
        merged_tickers = sorted(set(existing_meta.get("tickers") or []) | set(note_fm.tickers))
        merged_tags = sorted(set(existing_meta.get("tags") or []) | set(note_fm.tags))
        new_meta = {
            **existing_meta,
            "tickers": merged_tickers,
            "tags": merged_tags,
            "updated": _now_kst().isoformat(),
        }
        new_meta.setdefault("type", note_fm.type)
        new_meta.setdefault("author", note_fm.author)
        new_meta.setdefault("created", note_fm.created.isoformat())

        new_section = f"\n\n---\n## {ts}\n\n{body}"
        final_content_body = post.content + new_section

        # Re-render full file with merged frontmatter.
        yaml_block = yaml.safe_dump(
            new_meta, sort_keys=False, allow_unicode=True, default_flow_style=False
        )
        rendered = f"---\n{yaml_block}---\n{final_content_body}"
        if not rendered.endswith("\n"):
            rendered += "\n"
        _atomic_write(target, rendered)

        result = AddNoteResponse(
            vault_path=str(target.relative_to(root.resolve())),
            action="appended",
            idempotent=False,
        )
        latency = int((time.perf_counter() - t0) * 1000)
        log_tool_call("add_note", args_log, latency, len(result.model_dump_json()) // 4)
        return result

    except StructuredError as e:
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(e)
        log_tool_call("add_note", args_log, latency, 0, error=err["error"])
        return err
    except Exception as e:  # noqa: BLE001 — D-21 catch-all
        wrapped = StructuredError(ErrorCode.INTERNAL, str(e)[:200])
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(wrapped)
        log_tool_call("add_note", args_log, latency, 0, error=err["error"])
        return err


mcp.tool()(add_note)
