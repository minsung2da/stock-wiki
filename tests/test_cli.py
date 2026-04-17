"""CLI tests (Phase 3 Plan 06 — Task 1).

Exercises ``cli.__main__:main`` via in-process monkeypatching of the domain
modules (collect_dart, ingest_run, rebuild_from_vault). No testcontainer / no
real DB / no bge-m3 download. Every subcommand path is asserted:

* C1 --help lists subcommands (no handler dispatch)
* C2 collect dart delegates to collectors.dart.collect_dart with parsed args
* C3 ingest run delegates to ingest.worker.ingest_run with the engine
* C4 ingest rebuild (--yes) delegates to ingest.rebuild.rebuild_from_vault
* C5 ingest rebuild --dry-run does NOT touch the DB (delegates but marker-dict)
* C6 ingest rebuild without --yes on TTY returns exit 2 on user 'n'
* C7 ingest rebuild --yes skips TTY prompt
* C8 --force-reembed flag propagates to ingest_run / rebuild_from_vault
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from cli import commands as cmd_mod
from cli.__main__ import build_parser, main

# ---------- C1: --help lists subcommands ----------


def test_C1_help_lists_subcommands(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "collect" in out
    assert "ingest" in out


def test_C1b_ingest_help_lists_run_and_rebuild(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["ingest", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "run" in out
    assert "rebuild" in out


# ---------- C2: collect dart delegates ----------


def test_C2_collect_dart_delegates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path: Path
) -> None:
    captured: dict = {}
    sentinel_engine = object()

    def fake_collect_dart(*, corp_code, since, max_docs, vault_root, engine):  # noqa: ANN001
        captured["corp_code"] = corp_code
        captured["since"] = since
        captured["max_docs"] = max_docs
        captured["vault_root"] = vault_root
        captured["engine"] = engine
        return {"total": 5, "succeeded": 5, "skipped": 0, "failed": []}

    # cmd_collect_dart imports collect_dart + get_engine lazily at call time
    import collectors.dart as dart_mod
    import db.engine as engine_mod

    monkeypatch.setattr(dart_mod, "collect_dart", fake_collect_dart)
    monkeypatch.setattr(engine_mod, "get_engine", lambda: sentinel_engine)

    exit_code = main(
        [
            "--vault-root",
            str(tmp_path),
            "collect",
            "dart",
            "--corp-code=00126380",
            "--since=2026-01-01",
            "--max-docs=5",
        ]
    )
    assert exit_code == 0
    assert captured["corp_code"] == "00126380"
    assert captured["since"] == "2026-01-01"
    assert captured["max_docs"] == 5
    assert captured["vault_root"] == tmp_path
    assert captured["engine"] is sentinel_engine
    out = capsys.readouterr().out
    assert json.loads(out)["succeeded"] == 5


# ---------- C3: ingest run delegates ----------


def test_C3_ingest_run_delegates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path: Path
) -> None:
    captured: dict = {}
    sentinel_engine = object()

    def fake_get_engine():
        return sentinel_engine

    def fake_ingest_run(vault_root, engine, *, force_reembed=False):  # noqa: ANN001
        captured["vault_root"] = vault_root
        captured["engine"] = engine
        captured["force_reembed"] = force_reembed
        return {"total": 0, "succeeded": 0, "skipped": 0, "failed": []}

    import db.engine as engine_mod
    import ingest.worker as worker_mod

    monkeypatch.setattr(engine_mod, "get_engine", fake_get_engine)
    monkeypatch.setattr(worker_mod, "ingest_run", fake_ingest_run)

    exit_code = main(["--vault-root", str(tmp_path), "ingest", "run"])
    assert exit_code == 0
    assert captured["vault_root"] == tmp_path
    assert captured["engine"] is sentinel_engine
    assert captured["force_reembed"] is False
    out = capsys.readouterr().out
    assert json.loads(out) == {"total": 0, "succeeded": 0, "skipped": 0, "failed": []}


# ---------- C4: ingest rebuild (--yes) delegates ----------


def test_C4_ingest_rebuild_delegates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path: Path
) -> None:
    captured: dict = {}
    sentinel_engine = object()

    def fake_get_engine():
        return sentinel_engine

    def fake_rebuild(vault_root, engine, *, force_reembed=False, dry_run=False, assume_yes=False):  # noqa: ANN001
        captured.update(
            {
                "vault_root": vault_root,
                "engine": engine,
                "force_reembed": force_reembed,
                "dry_run": dry_run,
                "assume_yes": assume_yes,
            }
        )
        return {"wiped": {}, "rebuilt": {}, "ingest_stats": {}}

    import db.engine as engine_mod
    import ingest.rebuild as rebuild_mod

    monkeypatch.setattr(engine_mod, "get_engine", fake_get_engine)
    monkeypatch.setattr(rebuild_mod, "rebuild_from_vault", fake_rebuild)

    exit_code = main(["--vault-root", str(tmp_path), "ingest", "rebuild", "--yes"])
    assert exit_code == 0
    assert captured["assume_yes"] is True
    assert captured["dry_run"] is False
    assert captured["force_reembed"] is False
    out = capsys.readouterr().out
    assert json.loads(out)["ingest_stats"] == {}


# ---------- C5: dry-run propagates ----------


def test_C5_ingest_rebuild_dry_run_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict = {}

    import db.engine as engine_mod
    import ingest.rebuild as rebuild_mod

    monkeypatch.setattr(engine_mod, "get_engine", lambda: object())
    monkeypatch.setattr(
        rebuild_mod,
        "rebuild_from_vault",
        lambda *a, **kw: (captured.update(kw), {"dry_run": True})[1],
    )

    exit_code = main(["--vault-root", str(tmp_path), "ingest", "rebuild", "--dry-run"])
    assert exit_code == 0
    assert captured["dry_run"] is True


# ---------- C6 / C7: aborted exit code ----------


def test_C6_ingest_rebuild_aborted_returns_exit_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import db.engine as engine_mod
    import ingest.rebuild as rebuild_mod

    monkeypatch.setattr(engine_mod, "get_engine", lambda: object())
    monkeypatch.setattr(rebuild_mod, "rebuild_from_vault", lambda *a, **kw: {"aborted": True})

    exit_code = main(["--vault-root", str(tmp_path), "ingest", "rebuild"])
    assert exit_code == 2


def test_C7_ingest_rebuild_yes_propagates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict = {}

    import db.engine as engine_mod
    import ingest.rebuild as rebuild_mod

    monkeypatch.setattr(engine_mod, "get_engine", lambda: object())
    monkeypatch.setattr(
        rebuild_mod,
        "rebuild_from_vault",
        lambda *a, **kw: (captured.update(kw), {"wiped": {}, "rebuilt": {}, "ingest_stats": {}})[1],
    )

    exit_code = main(["--vault-root", str(tmp_path), "ingest", "rebuild", "--yes"])
    assert exit_code == 0
    assert captured["assume_yes"] is True


# ---------- C8: --force-reembed on both ingest run and rebuild ----------


def test_C8_force_reembed_flag_on_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict = {}

    import db.engine as engine_mod
    import ingest.worker as worker_mod

    monkeypatch.setattr(engine_mod, "get_engine", lambda: object())

    def fake_ingest_run(vault_root, engine, *, force_reembed=False):  # noqa: ANN001
        captured["force_reembed"] = force_reembed
        return {}

    monkeypatch.setattr(worker_mod, "ingest_run", fake_ingest_run)

    exit_code = main(["--vault-root", str(tmp_path), "ingest", "run", "--force-reembed"])
    assert exit_code == 0
    assert captured["force_reembed"] is True


def test_C8b_force_reembed_flag_on_rebuild(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict = {}

    import db.engine as engine_mod
    import ingest.rebuild as rebuild_mod

    monkeypatch.setattr(engine_mod, "get_engine", lambda: object())
    monkeypatch.setattr(
        rebuild_mod,
        "rebuild_from_vault",
        lambda *a, **kw: (captured.update(kw), {"wiped": {}, "rebuilt": {}, "ingest_stats": {}})[1],
    )

    exit_code = main(
        [
            "--vault-root",
            str(tmp_path),
            "ingest",
            "rebuild",
            "--yes",
            "--force-reembed",
        ]
    )
    assert exit_code == 0
    assert captured["force_reembed"] is True


# ---------- Parser smoke test ----------


def test_build_parser_is_complete() -> None:
    p = build_parser()
    # argparse throws SystemExit on missing required subcommand
    with pytest.raises(SystemExit):
        p.parse_args([])


# Silence unused imports referenced only by monkeypatch paths
_ = (io, cmd_mod)
