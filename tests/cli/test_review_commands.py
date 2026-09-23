"""Review replay input validation must reject mistakes before DB or API access."""

from argparse import Namespace
from datetime import date

import pytest

from cli.__main__ import build_parser
from cli.review_commands import cmd_review_news, print_summary


@pytest.mark.parametrize(
    "until,limit",
    [(date(2026, 8, 31), 25), (date.max, 25), (date(2026, 9, 23), 0), (date(2026, 9, 23), 501)],
)
def test_invalid_replay_scope_does_not_open_db(until, limit, monkeypatch):
    monkeypatch.setattr("cli.review_commands.get_engine", lambda: pytest.fail("DB was opened"))
    assert cmd_review_news(Namespace(since=date(2026, 9, 1), until=until, limit=limit)) == 2


def test_review_parser_and_error_summary(capsys):
    args = build_parser().parse_args(
        ["review", "news", "--since", "2026-09-01", "--until", "2026-09-23", "--limit", "25"]
    )
    assert args.since == date(2026, 9, 1)
    assert args.func is cmd_review_news
    assert print_summary([{"status": "error", "error_code": "missing_source"}]) == 1
    assert "missing_source" in capsys.readouterr().out
