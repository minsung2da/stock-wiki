"""No-op heartbeat stub.

The original ``ingest.heartbeat`` module was removed during the LLM-wiki
shutdown (see git tag ``pre-llm-wiki-shutdown`` / branch
``archive/llm-wiki-2026-04``). Collectors still call ``record_source_run``
for runtime observability; this stub preserves their import contract until
the post-shutdown redesign decides on the replacement (DB row vs. structured
log vs. external metric).

Intentionally accepts any args/kwargs and returns ``None``.
"""

from __future__ import annotations

from typing import Any


def record_source_run(*args: Any, **kwargs: Any) -> None:
    """Placeholder for the removed ingest heartbeat writer.

    Original signature: ``record_source_run(source: str, stats: dict, *,
    heartbeat_path: Path, extra: dict | None = None, ...)``. Argument shape
    is preserved at call sites; this stub silently drops everything.
    """
    return None
