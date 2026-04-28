"""Phase 6 Plan 06-02 Task 3: repo_root() public helper tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from stock_mcp.repo_root import repo_root


def test_r1_walks_up_to_project_root_from_inside_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCK_REPO_ROOT", raising=False)
    # cwd defaults to the project root in pytest; if not, walk from src/ to find it.
    monkeypatch.chdir(Path(__file__).parent)
    r = repo_root()
    assert (r / "pyproject.toml").exists()
    assert (r / "vault").exists()
    assert r.is_absolute()


def test_r2_env_override_returns_resolved_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("STOCK_REPO_ROOT", str(tmp_path))
    r = repo_root()
    assert r == tmp_path.resolve()


def test_r3_env_override_nonexistent_path_still_returns_resolved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bogus = tmp_path / "does_not_exist"
    monkeypatch.setenv("STOCK_REPO_ROOT", str(bogus))
    r = repo_root()
    assert r == bogus.resolve()


def test_r4_outside_project_falls_back_to_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("STOCK_REPO_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    r = repo_root()
    assert r == tmp_path.resolve()


def test_r5_signature_and_exports() -> None:
    import inspect

    from stock_mcp import repo_root as module

    sig = inspect.signature(module.repo_root)
    assert list(sig.parameters) == []
    assert sig.return_annotation in (Path, "Path")
    assert module.__all__ == ["repo_root"]
