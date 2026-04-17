"""dart-fss client wrapper (COLL-06, D-01).

Encapsulates API-key initialization and corp lookup so the rest of the
collector can import `client.get_client()` / `client.find_corp()` without
touching environment variables directly.

No LLM libraries imported here (COLL-07). dart-fss is imported lazily inside
each function so unit tests can monkeypatch `client.find_corp` before
dart-fss is ever loaded.
"""

from __future__ import annotations

import os
from typing import Any


class CollectorConfigError(RuntimeError):
    """Raised when the collector is misconfigured (e.g., missing API key).

    Never includes the secret value itself in the message (T-3-03 mitigation).
    """


_initialized = False


def _reset() -> None:
    """Reset the module-level initialization flag.

    Test-only helper: call this in test fixtures that unset DART_API_KEY so
    subsequent calls to get_client() re-read the environment variable rather
    than returning silently from the cached _initialized=True state.

    Not intended for production use — the API key does not change at runtime.
    """
    global _initialized
    _initialized = False


def get_client() -> None:
    """Initialize dart-fss with the API key from `DART_API_KEY` env var.

    Memoized: repeated calls are cheap after the first successful init.
    Raises CollectorConfigError if the key is absent — callers must handle.
    """
    global _initialized
    if _initialized:
        return

    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        raise CollectorConfigError("DART_API_KEY not set")

    import dart_fss  # lazy import so tests can monkeypatch before loading

    dart_fss.set_api_key(api_key=api_key)
    _initialized = True


def find_corp(corp_code: str) -> Any:
    """Resolve an 8-digit DART corp_code to a dart-fss Corp object.

    Thin wrapper so tests can monkeypatch this function without touching
    dart_fss internals.
    """
    import dart_fss

    return dart_fss.get_corp_list().find_by_corp_code(corp_code)
