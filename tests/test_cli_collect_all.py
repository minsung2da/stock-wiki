"""CLI tests for Phase 4 Plan 06 — `stock collect {krx,news,macro,kind,all}`.

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
            "succeeded": succeeded,
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
            "succeeded": 1,
            "skipped": 0,
            "failed": [{"doc": "x", "error": "nope"}],
            "elapsed_ms": 1,
        }

    return _fn


def _patch_dispatch(monkeypatch: pytest.MonkeyPatch, mapping: dict) -> None:
    monkeypatch.setattr(cmd_mod, "_dispatch", lambda: mapping)
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
    assert json.loads(out)["succeeded"] == 3


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
            return {"succeeded": 1, "failed": [], "elapsed_ms": 1}

        return _fn

    _patch_dispatch(
        monkeypatch,
        {
            "krx": _make("krx"),
            "news": _make("news"),
            "macro": _make("macro"),
            "kind": _make("kind"),
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
            return {"succeeded": 1, "failed": [], "elapsed_ms": 1}

        return _fn

    _patch_dispatch(monkeypatch, {n: _make(n) for n in ("krx", "news", "macro", "kind")})
    exit_code = main(["collect", "all", "--sources=krx,nope"])
    assert exit_code == 2
    # No collectors ran
    assert called == []


# ---------- CA4: default --sources is {krx,news,macro,kind}, NOT dart ----------


def test_CA4_collect_all_default_excludes_dart(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    order: list[str] = []

    def _make(name: str):
        def _fn(**kwargs: Any) -> dict:
            order.append(name)
            return {"succeeded": 1, "failed": [], "elapsed_ms": 1}

        return _fn

    _patch_dispatch(
        monkeypatch,
        {
            "dart": _make("dart"),
            "krx": _make("krx"),
            "news": _make("news"),
            "macro": _make("macro"),
            "kind": _make("kind"),
        },
    )
    exit_code = main(["collect", "all"])
    assert exit_code == 0
    assert order == ["krx", "news", "macro", "kind"]
    assert "dart" not in order


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
            "kind": _fake_ok("kind"),
        },
    )
    exit_code = main(["collect", "all"])
    assert exit_code == 1
    err = capsys.readouterr().err
    # stderr carries exactly one JSON-parseable line
    json_line = [line for line in err.strip().splitlines() if line.strip().startswith("{")][-1]
    report = json.loads(json_line)
    assert set(report["sources"].keys()) == {"krx", "news", "macro", "kind"}
    assert report["sources"]["news"]["status"] == "error"
    assert "news boom" in report["sources"]["news"]["error"]
    assert report["sources"]["krx"]["status"] == "ok"
    assert report["sources"]["macro"]["status"] == "ok"
    assert report["sources"]["kind"]["status"] == "ok"


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
            "kind": _fake_ok("kind"),
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
            "kind": _fake_ok("kind", succeeded=1),
        },
    )
    exit_code = main(["collect", "all"])
    assert exit_code == 0
    err = capsys.readouterr().err
    json_line = [line for line in err.strip().splitlines() if line.strip().startswith("{")][-1]
    report = json.loads(json_line)
    assert "run_at" in report
    assert set(report["sources"].keys()) == {"krx", "news", "macro", "kind"}
    for src, docs in [("krx", 5), ("news", 7), ("macro", 2), ("kind", 1)]:
        entry = report["sources"][src]
        assert entry["status"] == "ok"
        assert entry["docs_processed"] == docs
        assert "elapsed_ms" in entry
        assert isinstance(entry["elapsed_ms"], int)
        # 01-02: writers still author files (no DB inserts), so the new
        # inserted/updated keys are present with default 0. Wave 1/2 collectors
        # surface real values once db_writer.* lands.
        assert entry.get("inserted") == 0, entry
        assert entry.get("updated") == 0, entry


# ---------- CA8: stderr JSON is machine-parseable ----------


def test_CA8_stderr_json_parseable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _patch_dispatch(
        monkeypatch,
        {n: _fake_ok(n) for n in ("krx", "news", "macro", "kind")},
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
    for sub in ("dart", "krx", "news", "macro", "kind", "all"):
        assert sub in out, f"missing subparser: {sub}"
