"""CLI parse tests for `stock collect fundamentals` — Plan 03-05 Task 2.

Pure argparse parse tests (NO db marker — runs under ``-m "not db"``). Builds the
parser via the ``build_parser`` factory (same as ``cli.__main__``), parses argv,
and asserts the namespace routes to ``cmd_collect_fundamentals`` with the parsed
``--since``. This file is the deterministic target for the verify command so
pytest cannot exit 0 on zero collected tests.
"""

from __future__ import annotations

import pytest

from cli.__main__ import build_parser
from cli.commands import cmd_collect_fundamentals


def test_collect_fundamentals_dispatches_with_since() -> None:
    """`collect fundamentals --since 2026-01-01` → cmd_collect_fundamentals, since parsed."""
    parser = build_parser()
    args = parser.parse_args(["collect", "fundamentals", "--since", "2026-01-01"])
    assert args.func is cmd_collect_fundamentals
    assert args.since == "2026-01-01"


def test_collect_fundamentals_registered_without_since() -> None:
    """`collect fundamentals` (no --since) parses; subcommand is registered."""
    parser = build_parser()
    args = parser.parse_args(["collect", "fundamentals"])
    assert args.func is cmd_collect_fundamentals
    assert args.since is None


def test_collect_unknown_subcommand_errors() -> None:
    """An unknown collect subcommand still errors (argparse SystemExit)."""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["collect", "definitely-not-a-source"])


def test_collect_fundamentals_in_help(capsys: pytest.CaptureFixture) -> None:
    """The `fundamentals` subparser is listed in `collect --help` and other
    subcommands are not regressed."""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["collect", "--help"])
    out = capsys.readouterr().out
    for sub in ("dart", "krx", "news", "macro", "fundamentals", "all"):
        assert sub in out, f"missing subparser in help: {sub}"
