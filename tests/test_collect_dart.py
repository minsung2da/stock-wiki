"""Tests for collect_dart (COLL-01/06/08/09, D-01/D-03/D-19).

Mocks dart-fss at the client/fetcher boundary so tests never touch the real
DART API. Each test asserts a specific behavior from the plan:
- A+B filings land in vault/raw/dart/YYYY/
- max_docs cap is respected (D-03)
- pblntf_ty=["A","B"] is the only filter used (D-01)
- Idempotent rerun on content_hash match (COLL-08)
- Changed body triggers re-write
- Heartbeat recorded on success + on failure
- Per-filing isolation on fetch error
- CI import-guard: no anthropic/openai anywhere under collectors/dart/
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml


@dataclass
class _FakeFiling:
    rcept_no: str
    rcept_dt: str  # "YYYYMMDD"
    pblntf_ty: str  # "A" or "B"
    body_text: str = "기본 본문"

    # dart-fss Report API shape — mocked via duck typing.
    @property
    def pages(self) -> list[Any]:
        return [_FakePage(self.body_text)]

    def to_dict(self, summary: bool = False) -> dict[str, Any]:
        return {"rcept_no": self.rcept_no, "text": self.body_text}


@dataclass
class _FakePage:
    text: str

    @property
    def html(self) -> str:
        return f"<p>{self.text}</p>"


@dataclass
class _FakeCorp:
    stock_code: str = "005930"
    last_search_kwargs: dict[str, Any] | None = None

    def search_filings(self, **kwargs: Any) -> Any:
        # Capture kwargs for test assertions (D-01 verification).
        self.last_search_kwargs = kwargs
        filings = list(self._all_filings)
        # Return a SearchResults-like stub with .report_list attribute.
        return _FakeSearchResults(filings)

    _all_filings: list[_FakeFiling] = None  # type: ignore[assignment]


@dataclass
class _FakeSearchResults:
    report_list: list[_FakeFiling]


@pytest.fixture
def mock_dart(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch client.get_client + client.find_corp; return shared state dict."""
    state: dict[str, Any] = {"corp": None, "filings": []}

    def _get_client() -> None:
        return None  # no-op

    def _find_corp(corp_code: str) -> _FakeCorp:
        corp = state["corp"]
        assert corp is not None, "test must set state['corp'] before calling collect_dart"
        return corp

    monkeypatch.setattr("collectors.dart.client.get_client", _get_client)
    monkeypatch.setattr("collectors.dart.client.find_corp", _find_corp)
    return state


def _make_corp(filings: list[_FakeFiling]) -> _FakeCorp:
    corp = _FakeCorp()
    corp._all_filings = filings
    return corp


class TestCollectDart:
    def test_collects_ab_filings_writes_files(
        self, tmp_path: Path, mock_dart: dict[str, Any]
    ) -> None:
        """Two fake A+B filings → two md files with provenance frontmatter."""
        filings = [
            _FakeFiling("20260101000001", "20260115", "A", body_text="A 본문"),
            _FakeFiling("20260101000002", "20260116", "B", body_text="B 본문"),
        ]
        mock_dart["corp"] = _make_corp(filings)

        from collectors.dart import collect_dart

        stats = collect_dart(corp_code="00126380", since="2026-01-01", vault_root=tmp_path)

        assert stats["succeeded"] == 2
        assert stats["failed"] == []

        path_a = tmp_path / "raw/dart/2026/20260101000001_00126380.md"
        path_b = tmp_path / "raw/dart/2026/20260101000002_00126380.md"
        assert path_a.exists()
        assert path_b.exists()

        # Frontmatter sanity on the first file.
        text = path_a.read_text(encoding="utf-8")
        end = text.find("\n---", 3)
        meta = yaml.safe_load(text[3:end])
        prov = meta["provenance"]
        assert prov["source"] == "dart"
        assert prov["corp_code"] == "00126380"
        assert prov["trust_level"] == "trusted"
        assert prov["content_hash"]  # non-null
        assert prov["source_id"] == "20260101000001"

    def test_max_docs_cap_respected(self, tmp_path: Path, mock_dart: dict[str, Any]) -> None:
        """200 filings + max_docs=100 → exactly 100 files written (D-03)."""
        filings = [
            _FakeFiling(f"202601010{i:05d}", "20260115", "A", body_text=f"본문 {i}")
            for i in range(200)
        ]
        mock_dart["corp"] = _make_corp(filings)

        from collectors.dart import collect_dart

        stats = collect_dart(
            corp_code="00126380",
            since="2026-01-01",
            max_docs=100,
            vault_root=tmp_path,
        )
        assert stats["total"] == 100
        assert stats["succeeded"] == 100
        written = list((tmp_path / "raw/dart/2026").glob("*.md"))
        assert len(written) == 100

    def test_only_ab_filing_types(self, tmp_path: Path, mock_dart: dict[str, Any]) -> None:
        """search_filings is called with pblntf_ty=['A','B'] (D-01)."""
        filings = [_FakeFiling("20260101000001", "20260115", "A")]
        corp = _make_corp(filings)
        mock_dart["corp"] = corp

        from collectors.dart import collect_dart

        collect_dart(corp_code="00126380", since="2026-01-01", vault_root=tmp_path)

        assert corp.last_search_kwargs is not None
        assert corp.last_search_kwargs.get("pblntf_ty") == ["A", "B"]

    def test_idempotent_rerun_skips_unchanged(
        self, tmp_path: Path, mock_dart: dict[str, Any]
    ) -> None:
        """Rerunning with identical bodies → all skipped (COLL-08)."""
        filings = [_FakeFiling("20260101000001", "20260115", "A", body_text="same")]
        mock_dart["corp"] = _make_corp(filings)

        from collectors.dart import collect_dart

        stats1 = collect_dart(corp_code="00126380", since="2026-01-01", vault_root=tmp_path)
        path = tmp_path / "raw/dart/2026/20260101000001_00126380.md"
        mtime1 = path.stat().st_mtime_ns

        stats2 = collect_dart(corp_code="00126380", since="2026-01-01", vault_root=tmp_path)
        mtime2 = path.stat().st_mtime_ns

        assert stats1["succeeded"] == 1
        assert stats2["skipped"] == 1
        assert stats2["succeeded"] == 0
        assert mtime1 == mtime2, "unchanged file should not be re-written"

    def test_changed_body_is_rewritten(self, tmp_path: Path, mock_dart: dict[str, Any]) -> None:
        """Modified body → content_hash differs → file rewritten."""
        from collectors.dart import collect_dart

        filings_v1 = [_FakeFiling("20260101000001", "20260115", "A", body_text="v1")]
        mock_dart["corp"] = _make_corp(filings_v1)
        collect_dart(corp_code="00126380", since="2026-01-01", vault_root=tmp_path)

        filings_v2 = [_FakeFiling("20260101000001", "20260115", "A", body_text="v2")]
        mock_dart["corp"] = _make_corp(filings_v2)
        stats2 = collect_dart(corp_code="00126380", since="2026-01-01", vault_root=tmp_path)
        assert stats2["succeeded"] >= 1
        assert stats2["skipped"] == 0

    def test_collector_records_heartbeat(self, tmp_path: Path, mock_dart: dict[str, Any]) -> None:
        """Successful run updates heartbeat.md sources.dart.last_success (COLL-09)."""
        filings = [_FakeFiling("20260101000001", "20260115", "A")]
        mock_dart["corp"] = _make_corp(filings)

        from collectors.dart import collect_dart

        stats = collect_dart(corp_code="00126380", since="2026-01-01", vault_root=tmp_path)

        hb = tmp_path / "ingested/_status/heartbeat.md"
        assert hb.exists()
        text = hb.read_text(encoding="utf-8")
        end = text.find("\n---", 3)
        meta = yaml.safe_load(text[3:end])
        dart = meta["sources"]["dart"]
        assert dart["last_success"]
        assert dart["docs_processed"] == stats["succeeded"]

    def test_collector_records_heartbeat_on_failure(
        self,
        tmp_path: Path,
        mock_dart: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Partial failure: good filing writes, failing one recorded; heartbeat.last_failure set."""
        filings = [
            _FakeFiling("20260101000001", "20260115", "A", body_text="good"),
            _FakeFiling("20260101000002", "20260115", "B", body_text="bad"),
        ]
        mock_dart["corp"] = _make_corp(filings)

        # Patch fetch_body to raise on the second filing.
        from collectors.dart import fetcher

        def flaky_fetch(filing: Any) -> str:
            if filing.rcept_no == "20260101000002":
                raise RuntimeError("network boom")
            return filing.body_text

        monkeypatch.setattr(fetcher, "fetch_body", flaky_fetch)

        from collectors.dart import collect_dart

        stats = collect_dart(corp_code="00126380", since="2026-01-01", vault_root=tmp_path)
        assert stats["succeeded"] == 1
        assert len(stats["failed"]) == 1
        assert "network boom" in stats["failed"][0]["error"]

        hb = tmp_path / "ingested/_status/heartbeat.md"
        text = hb.read_text(encoding="utf-8")
        end = text.find("\n---", 3)
        meta = yaml.safe_load(text[3:end])
        dart = meta["sources"]["dart"]
        assert dart["last_failure"]

    def test_ci_import_guard_passes(self) -> None:
        """No anthropic/openai imports in src/collectors/dart/ (COLL-06/07)."""
        banned = {"anthropic", "openai"}
        collectors_dart = Path(__file__).parent.parent / "src" / "collectors" / "dart"
        assert collectors_dart.exists()

        violations = []
        for py in collectors_dart.rglob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in banned:
                            violations.append(f"{py}:{alias.name}")
                elif (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and node.module.split(".")[0] in banned
                ):
                    violations.append(f"{py}:{node.module}")
        assert not violations, f"banned imports found: {violations}"
