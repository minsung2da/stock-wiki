"""``get_note`` — read a ``notes/private/`` memo from disk (read-only, wrapped).

``get_note(path)`` is the ONLY tool that touches the filesystem. It reads a user
thesis/journal memo from the gitignored ``notes/private/`` whitelist and returns
the WHOLE content (Veto #8) wrapped in the ``<untrusted>`` XML delimiter + injection
flags (D-03/SC#5).

Disk, NOT the ``notes`` DB table (D-05): even though Phase 3 also ingests
``notes/private/*.md`` into a ``notes`` table for ``hybrid_search``, ``get_note``
stays a direct read-only DISK read — the disk is the source of truth for a single
memo fetch (the table is a search index, refreshed by the ingest job).

Path safety (V12 / T-path-traversal): :func:`paths.safe_resolve` resolves the
caller path under the repo root (collapsing ``..`` and following symlinks) and
admits it ONLY inside ``notes/private/`` — raising :class:`NotePathForbidden` on an
escape and :class:`NoteNotFound` on a whitelisted-but-missing file.
"""

from __future__ import annotations

import re
from pathlib import Path

from mcp.types import ToolAnnotations

from .. import injection
from .._mcp import mcp
from ..models import NoteContent
from ..paths import safe_resolve

__all__ = ["get_note"]

# The repo root for the disk whitelist — the process cwd (the MCP server is
# launched from the repo root; tests pass paths relative to a tmp repo root).
_REPO_ROOT = Path(".")

# Characters NOT in the wrap_untrusted _SAFE_ATTR class ([A-Za-z0-9_:.-]). Path
# separators and anything else are collapsed to '_' so the delimiter ref attr is
# always well-formed (the path itself is still echoed verbatim in NoteContent.path).
_UNSAFE_REF_CHARS = re.compile(r"[^A-Za-z0-9_:.-]+")


def _ref_from_path(path: str) -> str:
    """A wrap_untrusted-safe ref derived from the note path.

    Replaces every char outside ``[A-Za-z0-9_:.-]`` with ``_`` and prefixes a
    stable ``note:`` provenance tag, so a path like ``notes/private/a/b.md``
    becomes ``note:notes_private_a_b.md`` (never empty, always _SAFE_ATTR-valid).
    """
    sanitized = _UNSAFE_REF_CHARS.sub("_", path).strip("_")
    return f"note:{sanitized or 'unnamed'}"


def get_note(path: str) -> NoteContent:
    """Read a ``notes/private/`` memo from disk and return it wrapped.

    Args:
        path: a repo-relative path inside ``notes/private/``.

    Returns:
        :class:`NoteContent` — the whole file content wrapped in ``<untrusted
        source="note" ref="...">`` (D-03) with advisory injection flags.

    Raises:
        NotePathForbidden: ``path`` resolves outside the ``notes/private/`` whitelist.
        NoteNotFound: ``path`` is whitelisted but the file does not exist.
    """
    resolved = safe_resolve(_REPO_ROOT, path)
    content = resolved.read_text(encoding="utf-8")

    flags = [h["pattern_id"] for h in injection.detect(content)]
    wrapped = injection.wrap_untrusted(content, "note", _ref_from_path(path))
    return NoteContent(
        path=path,
        content_md=wrapped,
        injection_suspected=bool(flags),
        injection_flags=flags,
    )


# Register on the shared mcp via the call form (keeps get_note a plain callable
# for in-process callers; see filing.py for the rationale).
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(get_note)
