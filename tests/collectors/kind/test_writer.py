"""Unit tests for collectors.kind.writer — vault path + idempotency."""

from __future__ import annotations

import pytest

from collectors.kind.writer import vault_path_for_kind, write_kind_event


def test_vault_path_shape(tmp_path):
    p = vault_path_for_kind(tmp_path, "suspension", "005930", "20260417")
    assert p == tmp_path / "raw" / "kind" / "2026-04" / "suspension_005930_20260417.md"


def test_vault_path_rejects_bad_event_type(tmp_path):
    with pytest.raises(ValueError):
        vault_path_for_kind(tmp_path, "weird", "005930", "20260417")


def test_vault_path_rejects_bad_ticker(tmp_path):
    with pytest.raises(ValueError):
        vault_path_for_kind(tmp_path, "suspension", "abcdef", "20260417")
    with pytest.raises(ValueError):
        vault_path_for_kind(tmp_path, "suspension", "12345", "20260417")


def test_vault_path_rejects_bad_event_date(tmp_path):
    with pytest.raises(ValueError):
        vault_path_for_kind(tmp_path, "suspension", "005930", "2026-04-17")


def test_write_kind_event_is_idempotent(tmp_path):
    kwargs = dict(
        vault_root=tmp_path,
        event_type="suspension",
        ticker="005930",
        event_date="20260417",
        corp_code="00126380",
        company_name="삼성전자",
        reason="주권매매거래정지",
        source="dart",
        source_id="20260417000001",
        source_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260417000001",
        subtype=None,
    )
    p1, h1, rewrote1 = write_kind_event(**kwargs)
    assert rewrote1 is True
    assert p1.exists()
    p2, h2, rewrote2 = write_kind_event(**kwargs)
    assert rewrote2 is False
    assert h2 == h1


def test_write_kind_event_trust_level_trusted(tmp_path):
    p, _, _ = write_kind_event(
        vault_root=tmp_path,
        event_type="unfaithful_disclosure",
        ticker="000660",
        event_date="20260415",
        corp_code="00164779",
        company_name="SK하이닉스",
        reason="불성실공시법인지정",
        source="dart",
        source_id="20260415000001",
        source_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260415000001",
    )
    text = p.read_text(encoding="utf-8")
    assert "trust_level: trusted" in text
    assert "source: kind" in text
    assert (
        "event_type: unfaithful_disclosure" not in text.splitlines()[0]
    )  # that's body not frontmatter title
