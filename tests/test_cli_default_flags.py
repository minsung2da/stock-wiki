"""CLI default-flag integration test — Gap-04-06 safety net.

Exercises `cli.__main__:main` with NO `--vault-root` flag to catch regressions
like Gap-04-03 (default pointed at repo root, not vault/). Uses a tmp_path
vault + monkeypatched collector dispatch so the CLI's argparse defaults are
the system-under-test, not the collector internals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def _seed_vault(root: Path) -> None:
    (root / "vault" / "notes").mkdir(parents=True)
    # Phase 6 P-01: portfolio at <repo_root>/notes/private/portfolio.md
    (root / "notes" / "private").mkdir(parents=True)
    (root / "notes" / "private" / "portfolio.md").write_text(
        "---\nwatchlist:\n  - ticker: '005930'\n    name: Samsung\nholdings: []\n---\n",
        encoding="utf-8",
    )


def test_default_vault_root_help_mentions_vault() -> None:
    """--help output documents default: vault (not default: .)."""
    from cli.__main__ import build_parser

    parser = build_parser()
    help_text = parser.format_help()
    assert "default: vault" in help_text, f"Expected 'default: vault' in --help; got:\n{help_text}"


def test_default_vault_root_resolves_portfolio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running `collect all --sources=krx` with NO --vault-root must see
    vault_root='vault' and reach the krx collector dispatch."""
    _seed_vault(tmp_path)

    captured: dict[str, Any] = {}

    def fake_collect_krx(**kwargs: Any) -> dict:
        captured["vault_root"] = str(kwargs.get("vault_root"))
        return {"total": 0, "succeeded": 0, "skipped": 0, "failed": [], "elapsed_ms": 1}

    from cli import commands as cmd_mod

    monkeypatch.setattr(cmd_mod, "_dispatch", lambda: {"krx": fake_collect_krx})
    monkeypatch.setattr(cmd_mod, "_engine", lambda: object())
    monkeypatch.chdir(tmp_path)

    from cli.__main__ import main

    exit_code = main(["collect", "all", "--sources=krx"])

    assert exit_code == 0
    # vault_root came from the argparse default; must equal "vault" (not ".")
    assert captured["vault_root"] == "vault", (
        f"Expected vault_root='vault', got {captured['vault_root']!r}. "
        "Gap-04-03 regression: --vault-root default pointed at repo root."
    )
