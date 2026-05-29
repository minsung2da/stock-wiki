"""CI guard: shared.heartbeat must stay deleted (Plan 01-08 Task 3, SC-3).

The v1.0 ``src/shared/heartbeat.py`` was a no-op stub from the LLM-wiki
shutdown. Phase 1 Plan 01-08 deletes it and routes observability through
``shared.run_log`` + structured stderr logs (RESEARCH.md Q5).

This guard:

1. ``test_heartbeat_module_not_on_disk`` — the file must not exist on disk.
2. ``test_no_collector_imports_heartbeat`` — no collector module imports
   anything called ``heartbeat``.
3. ``test_heartbeat_not_importable`` — ``import shared.heartbeat`` raises
   ``ModuleNotFoundError`` (defense-in-depth against shadow modules).

Runs in the default ``pytest -m 'not slow and not e2e'`` pass.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COLLECTOR_DIRS = ("dart", "krx", "news", "macro", "kind")


def test_heartbeat_module_not_on_disk() -> None:
    """``src/shared/heartbeat.py`` must remain deleted (SC-3 fence)."""
    target = _REPO_ROOT / "src" / "shared" / "heartbeat.py"
    assert not target.exists(), (
        "src/shared/heartbeat.py resurrected — per Phase 1 SC-3 it must "
        "stay deleted. Use shared.run_log.record_collector_run instead."
    )


def test_no_collector_imports_heartbeat() -> None:
    """No collector module may import anything named ``heartbeat``.

    Scans every .py file under ``src/collectors/<src>/`` and walks the AST
    for ``Import`` / ``ImportFrom`` nodes referencing ``heartbeat``.
    Mentions in docstrings are fine — they aren't import statements.
    """
    offenders: list[str] = []
    for src in _COLLECTOR_DIRS:
        for py in (_REPO_ROOT / "src" / "collectors" / src).rglob("*.py"):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module and "heartbeat" in node.module:
                        offenders.append(f"{py}:{node.lineno}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if "heartbeat" in alias.name:
                            offenders.append(f"{py}:{node.lineno}")
    assert not offenders, (
        "collectors importing heartbeat (use shared.run_log instead): "
        + ", ".join(offenders)
    )


def test_heartbeat_not_importable() -> None:
    """``import shared.heartbeat`` raises ModuleNotFoundError."""
    # ``find_spec`` returns None when the module cannot be located; this
    # is preferable to a try/except on import because it does NOT execute
    # any __init__ side effects of a hypothetical shadow module.
    spec = importlib.util.find_spec("shared.heartbeat")
    assert spec is None, (
        "shared.heartbeat is importable; expected ModuleNotFoundError. "
        f"Found at: {getattr(spec, 'origin', '<no origin>')}"
    )

    # Belt-and-suspenders: attempt the actual import; expect failure.
    try:
        importlib.import_module("shared.heartbeat")
    except ModuleNotFoundError:
        pass
    else:
        raise AssertionError(
            "import shared.heartbeat succeeded; the stub must remain deleted"
        )
