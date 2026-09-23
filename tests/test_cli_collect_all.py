"""CLI tests for Phase 4 Plan 06 — `stock collect {dart,krx,news,macro,fundamentals,all}`.

Exercises ``cli.__main__:main`` via in-process monkeypatching of
``cli.commands._dispatch`` to inject fake collector callables. No network, no
DB, no sentence-transformers. Every D-18..D-21 behavior is asserted.

Plan 01-02 (Wave 0): ``--vault-root`` flag removed from argparse; the fakes
no longer receive a ``vault_root`` kwarg, and every CLI invocation drops
``["--vault-root", str(tmp_path)]`` from its argv. Each `cmd_collect_all`
per-source entry now exposes ``inserted`` / ``updated`` (default 0 until
Wave 1/2 collectors emit real values).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from cli import commands as cmd_mod
from cli.__main__ import main


def _fake_ok(name: str, *, succeeded: int = 3) -> Any:
    """Build a fake collector that records the call and returns canned stats."""
    calls: list[dict] = []

    def _fn(**kwargs: Any) -> dict:
        calls.append({"name": name, "kwargs": kwargs})
        return {
            "total": succeeded,
            "inserted": succeeded,
            "skipped": 0,
            "failed": [],
            "elapsed_ms": 1,
        }

    _fn.calls = calls  # type: ignore[attr-defined]
    return _fn


def _fake_fail(name: str) -> Any:
    def _fn(**kwargs: Any) -> dict:
        raise RuntimeError(f"{name} boom")

    return _fn


def _fake_partial(name: str) -> Any:
    def _fn(**kwargs: Any) -> dict:
        return {
            "total": 2,
            "inserted": 1,
            "skipped": 0,
            "failed": [{"doc": "x", "error": "nope"}],
            "elapsed_ms": 1,
        }

    return _fn


def _patch_dispatch(monkeypatch: pytest.MonkeyPatch, mapping: dict) -> None:
    mapping.setdefault("dart", _fake_ok("dart"))
    monkeypatch.setattr(cmd_mod, "_dispatch", lambda: mapping)
    from types import SimpleNamespace

    import db.entity
    from shared.portfolio import Portfolio

    monkeypatch.setattr(
        Portfolio, "load", lambda root: SimpleNamespace(scope_tickers=lambda: ["005930"])
    )
    monkeypatch.setattr(
        db.entity,
        "resolve_entities",
        lambda engine, scope: {"005930": SimpleNamespace(corp_code="00126380")},
    )
    monkeypatch.setattr(cmd_mod, "_engine", lambda: object())


# ---------- CA1: stock collect krx exit 0 ----------


def test_CA1_collect_krx_exit_0(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    fake = _fake_ok("krx")
    _patch_dispatch(monkeypatch, {"krx": fake})
    exit_code = main(["collect", "krx"])
    assert exit_code == 0
    assert len(fake.calls) == 1  # type: ignore[attr-defined]
    # 01-02: fake never receives vault_root since the flag is gone.
    assert "vault_root" not in fake.calls[0]["kwargs"], fake.calls[0]["kwargs"]  # type: ignore[attr-defined]
    out = capsys.readouterr().out
    assert json.loads(out)["inserted"] == 3


def test_CA1b_collect_krx_exit_1_on_failed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _patch_dispatch(monkeypatch, {"krx": _fake_partial("krx")})
    exit_code = main(["collect", "krx"])
    assert exit_code == 1


# ---------- CA2: stock collect all --sources=krx,news order ----------


def test_CA2_collect_all_subset_order(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    order: list[str] = []
    captured_kwargs: dict[str, dict[str, Any]] = {}

    def _make(name: str):
        def _fn(**kwargs: Any) -> dict:
            order.append(name)
            captured_kwargs[name] = kwargs
            return {"inserted": 1, "failed": [], "elapsed_ms": 1}

        return _fn

    _patch_dispatch(
        monkeypatch,
        {
            "krx": _make("krx"),
            "news": _make("news"),
            "macro": _make("macro"),
            "fundamentals": _make("fundamentals"),
        },
    )
    exit_code = main(["collect", "all", "--sources=krx,news"])
    assert exit_code == 0
    assert order == ["krx", "news"]
    # 01-02: dispatch kwargs no longer carry vault_root.
    for name in ("krx", "news"):
        assert "vault_root" not in captured_kwargs[name], captured_kwargs[name]


# ---------- CA3: unknown --sources entry fails fast with exit 2 ----------


def test_CA3_collect_all_unknown_source_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    called: list[str] = []

    def _make(name: str):
        def _fn(**kwargs: Any) -> dict:
            called.append(name)
            return {"inserted": 1, "failed": [], "elapsed_ms": 1}

        return _fn

    _patch_dispatch(monkeypatch, {n: _make(n) for n in ("krx", "news", "macro", "fundamentals")})
    exit_code = main(["collect", "all", "--sources=krx,nope"])
    assert exit_code == 2
    # No collectors ran
    assert called == []


# ---------- CA4: default --sources includes all active collectors ----------


def test_CA4_collect_all_default_includes_dart(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    order: list[str] = []

    def _make(name: str):
        def _fn(**kwargs: Any) -> dict:
            order.append(name)
            return {"inserted": 1, "failed": [], "elapsed_ms": 1}

        return _fn

    _patch_dispatch(
        monkeypatch,
        {
            "dart": _make("dart"),
            "krx": _make("krx"),
            "news": _make("news"),
            "macro": _make("macro"),
            "fundamentals": _make("fundamentals"),
        },
    )
    exit_code = main(["collect", "all"])
    assert exit_code == 0
    assert order == ["dart", "krx", "news", "macro", "fundamentals"]
    assert "dart" in order


# ---------- CA5: one collector raises → caught, others run, exit 1 ----------


def test_CA5_collect_all_isolates_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _patch_dispatch(
        monkeypatch,
        {
            "krx": _fake_ok("krx"),
            "news": _fake_fail("news"),
            "macro": _fake_ok("macro"),
            "fundamentals": _fake_ok("fundamentals"),
        },
    )
    exit_code = main(["collect", "all"])
    assert exit_code == 1
    err = capsys.readouterr().err
    # stderr carries exactly one JSON-parseable line
    json_line = [line for line in err.strip().splitlines() if line.strip().startswith("{")][-1]
    report = json.loads(json_line)
    assert set(report["sources"].keys()) == {"dart", "krx", "news", "macro", "fundamentals"}
    assert report["sources"]["news"]["status"] == "error"
    assert "news boom" in report["sources"]["news"]["error"]
    assert report["sources"]["krx"]["status"] == "ok"
    assert report["sources"]["macro"]["status"] == "ok"
    assert report["sources"]["fundamentals"]["status"] == "ok"


# ---------- CA6: stats['failed'] non-empty → status='partial', exit 1 ----------


def test_CA6_collect_all_partial_marks_exit_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _patch_dispatch(
        monkeypatch,
        {
            "krx": _fake_ok("krx"),
            "news": _fake_partial("news"),
            "macro": _fake_ok("macro"),
            "fundamentals": _fake_ok("fundamentals"),
        },
    )
    exit_code = main(["collect", "all"])
    assert exit_code == 1
    err = capsys.readouterr().err
    json_line = [line for line in err.strip().splitlines() if line.strip().startswith("{")][-1]
    report = json.loads(json_line)
    assert report["sources"]["news"]["status"] == "partial"
    assert report["sources"]["krx"]["status"] == "ok"


# ---------- CA7: all succeed → exit 0 + schema ----------


def test_CA7_collect_all_success_schema(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _patch_dispatch(
        monkeypatch,
        {
            "krx": _fake_ok("krx", succeeded=5),
            "news": _fake_ok("news", succeeded=7),
            "macro": _fake_ok("macro", succeeded=2),
            "fundamentals": _fake_ok("fundamentals", succeeded=1),
        },
    )
    exit_code = main(["collect", "all"])
    assert exit_code == 0
    err = capsys.readouterr().err
    json_line = [line for line in err.strip().splitlines() if line.strip().startswith("{")][-1]
    report = json.loads(json_line)
    assert "run_at" in report
    assert set(report["sources"].keys()) == {"dart", "krx", "news", "macro", "fundamentals"}
    for src, docs in [("krx", 5), ("news", 7), ("macro", 2), ("fundamentals", 1)]:
        entry = report["sources"][src]
        assert entry["status"] == "ok"
        assert entry["docs_processed"] == docs
        assert "elapsed_ms" in entry
        assert isinstance(entry["elapsed_ms"], int)
        # Real collector insertion counters appear in the report.
        assert entry.get("inserted") == docs, entry
        assert entry.get("updated") == 0, entry


# ---------- CA8: stderr JSON is machine-parseable ----------


def test_CA8_stderr_json_parseable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _patch_dispatch(
        monkeypatch,
        {n: _fake_ok(n) for n in ("krx", "news", "macro", "fundamentals")},
    )
    main(["collect", "all"])
    err = capsys.readouterr().err
    json_line = [line for line in err.strip().splitlines() if line.strip().startswith("{")][-1]
    # Must parse without raising
    json.loads(json_line)


# ---------- CA9: collect dart still works (backward compat, D-18) ----------


def test_CA9_collect_dart_backward_compat(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    captured: dict = {}
    sentinel_engine = object()

    # 01-02 Task 2: collect_dart is keyword-only; vault_root has been removed.
    def fake_collect_dart(*, corp_code, since, max_docs, engine):  # noqa: ANN001
        captured["corp_code"] = corp_code
        captured["since"] = since
        captured["max_docs"] = max_docs
        captured["engine_is_sentinel"] = engine is sentinel_engine
        return {"total": 2, "succeeded": 2, "skipped": 0, "failed": []}

    import collectors.dart as dart_mod
    import db.engine as engine_mod

    monkeypatch.setattr(dart_mod, "collect_dart", fake_collect_dart)
    monkeypatch.setattr(engine_mod, "get_engine", lambda: sentinel_engine)

    exit_code = main(
        [
            "collect",
            "dart",
            "--corp-code=00126380",
            "--since=2026-01-01",
            "--max-docs=2",
        ]
    )
    assert exit_code == 0
    assert captured["corp_code"] == "00126380"
    assert captured["since"] == "2026-01-01"
    assert captured["max_docs"] == 2
    assert captured["engine_is_sentinel"] is True


# ---------- CA10: all four subparsers present in --help ----------


def test_CA10_collect_help_lists_new_subparsers(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit):
        main(["collect", "--help"])
    out = capsys.readouterr().out
    for sub in ("dart", "krx", "news", "macro", "fundamentals", "all"):
        assert sub in out, f"missing subparser: {sub}"


def test_batch_date_and_corporation_isolation(monkeypatch, capsys):
    from types import SimpleNamespace

    import db.entity
    from shared.portfolio import Portfolio

    calls = []

    def dart(**kwargs):
        calls.append(kwargs)
        if kwargs["corp_code"] == "001":
            raise RuntimeError("provider failure")
        return {"inserted": 2, "updated": 1, "skipped": 3, "failed": []}

    fund = _fake_ok("fundamentals")
    _patch_dispatch(monkeypatch, {"dart": dart, "fundamentals": fund})
    monkeypatch.setattr(
        Portfolio,
        "load",
        lambda root: SimpleNamespace(scope_tickers=lambda: ["a", "b", "c", "missing"]),
    )
    monkeypatch.setattr(
        db.entity,
        "resolve_entities",
        lambda engine, scope: {
            "a": SimpleNamespace(corp_code="001"),
            "b": SimpleNamespace(corp_code="002"),
            "c": SimpleNamespace(corp_code="002"),
        },
    )
    assert main(["collect", "all", "--sources=dart,fundamentals", "--since=2026-04-20"]) == 1
    assert [call["corp_code"] for call in calls] == ["001", "002"]
    assert all(call["since"] == "2026-04-20" for call in calls)
    assert fund.calls[0]["kwargs"]["since"] == "2026-04-20"
    report = json.loads(capsys.readouterr().err)
    assert report["sources"]["dart"]["failed_count"] == 2
    assert report["sources"]["dart"]["docs_processed"] == 6


@pytest.mark.parametrize("argv", [["--sources=kind"], ["--sources=,"], ["--since=2026-02-30"]])
def test_bad_batch_arguments_fail_before_engine(monkeypatch, argv):
    def forbidden():
        pytest.fail("engine must not be created for invalid arguments")

    monkeypatch.setattr(cmd_mod, "_engine", forbidden)
    assert main(["collect", "all", *argv]) == 2


def test_kind_command_removed():
    with pytest.raises(SystemExit) as result:
        main(["collect", "kind"])
    assert result.value.code == 2


def test_default_date_shared_and_duplicate_sources_run_once(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    krx, news, fund = (_fake_ok(name) for name in ("krx", "news", "fundamentals"))
    _patch_dispatch(monkeypatch, {"krx": krx, "news": news, "fundamentals": fund})
    before = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    assert main(["collect", "all", "--sources=krx,news,fundamentals,krx"]) == 0
    dates = {fake.calls[0]["kwargs"]["since"] for fake in (krx, news, fund)}
    after = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    assert len(dates) == 1 and dates <= {before, after}
    assert len(krx.calls) == 1
