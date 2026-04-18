"""KRX writer unit tests — COLL-02 / Plan 02 Task 1 behavior contract."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from collectors.krx.writer import (
    compute_body_hash,
    vault_path_for_krx,
    write_krx_doc,
)
from shared.frontmatter import read_frontmatter

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "krx"


def _load_ohlcv() -> pd.DataFrame:
    return pd.read_json(FIXTURES / "ohlcv_005930.json")


def _load_flow() -> pd.DataFrame:
    return pd.read_json(FIXTURES / "trading_value_005930.json")


def _load_short() -> pd.DataFrame:
    return pd.read_json(FIXTURES / "shorting_balance_005930.json")


def test_write_creates_file_with_expected_frontmatter(tmp_path: Path) -> None:
    path, content_hash = write_krx_doc(
        vault_root=tmp_path,
        ticker="005930",
        date_iso="2026-04-17",
        corp_code="00126380",
        company_name="삼성전자",
        ohlcv=_load_ohlcv(),
        flow=_load_flow(),
        short=_load_short(),
    )
    assert path.exists()
    assert path == tmp_path / "raw" / "krx" / "2026-04-17" / "005930.md"
    assert len(content_hash) == 64

    fm, _body = read_frontmatter(str(path))
    assert fm.provenance.source == "krx"
    assert fm.provenance.trust_level == "trusted"
    assert fm.provenance.corp_code == "00126380"
    assert fm.provenance.ticker == "005930"
    assert fm.provenance.date == "2026-04-17"
    assert fm.provenance.content_hash == content_hash
    assert fm.provenance.source_id == "005930_2026-04-17"


def test_body_contains_three_sections(tmp_path: Path) -> None:
    path, _ = write_krx_doc(
        vault_root=tmp_path,
        ticker="005930",
        date_iso="2026-04-17",
        corp_code="00126380",
        company_name="삼성전자",
        ohlcv=_load_ohlcv(),
        flow=_load_flow(),
        short=_load_short(),
    )
    text = path.read_text(encoding="utf-8")
    assert "## OHLCV" in text
    assert "## Investor Flow (KRW 순매수)" in text
    assert "## Short Balance" in text
    # to_markdown(index=True) emits a pipe-delimited table header.
    # A tabulate-rendered table always starts with '|' after the section title.
    assert "|" in text


def test_bad_ticker_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bad ticker"):
        vault_path_for_krx(tmp_path, "2026-04-17", "abc")


def test_path_traversal_ticker_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bad ticker"):
        vault_path_for_krx(tmp_path, "2026-04-17", "../etc")


def test_bad_date_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bad date"):
        vault_path_for_krx(tmp_path, "20260417", "005930")


def test_compute_body_hash_deterministic() -> None:
    body = "## OHLCV\n\n|  | 시가 |\n|--|--|\n| 20260417 | 70000 |\n"
    assert compute_body_hash(body) == compute_body_hash(body)


def test_hash_changes_when_inputs_change(tmp_path: Path) -> None:
    ohlcv1 = _load_ohlcv()
    ohlcv2 = ohlcv1.copy()
    ohlcv2.loc["20260417", "종가"] = 99999  # mutate a cell
    _, h1 = write_krx_doc(
        vault_root=tmp_path,
        ticker="005930",
        date_iso="2026-04-17",
        corp_code="00126380",
        company_name="삼성전자",
        ohlcv=ohlcv1,
        flow=_load_flow(),
        short=_load_short(),
    )
    _, h2 = write_krx_doc(
        vault_root=tmp_path,
        ticker="000660",
        date_iso="2026-04-17",
        corp_code="00164742",
        company_name="SK하이닉스",
        ohlcv=ohlcv2,
        flow=_load_flow(),
        short=_load_short(),
    )
    assert h1 != h2


def test_fixtures_load_as_dataframes() -> None:
    ohlcv = _load_ohlcv()
    flow = _load_flow()
    short = _load_short()
    assert set(["시가", "고가", "저가", "종가", "거래량"]).issubset(ohlcv.columns)
    assert list(flow.columns) == ["외국인", "기관합계", "개인"]
    assert "공매도잔고(주)" in short.columns
