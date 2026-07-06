"""src/analysis — Phase 4 analysis runner (3-role Bull/Bear/Judge debate).

The analysis brain compresses evidence into a ``decision_card``; it never predicts
price (Veto #1) and never self-certifies its own numbers (Veto #4 — the D-03 numeric
checksum in ``checksum.py`` is a deterministic Python gate that drops any LLM-emitted
numeric fact not derivable from source).

D-01 (Max-only Veto): every path to Sonnet goes through the headless ``claude`` CLI
subprocess under Max-subscription OAuth — this package must NEVER import a cloud-LLM
SDK (``anthropic`` / ``openai``); ``tests/test_import_guard.py`` enforces that in CI.

Wave 0 scaffold. A later plan re-exports ``analyze_ticker`` here:

    from .runner import analyze_ticker
    __all__ = ["analyze_ticker"]
"""

from __future__ import annotations

__all__: list[str] = []
