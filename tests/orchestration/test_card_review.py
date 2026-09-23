"""Citation-isolated shadow review; fake backend only, no API requests."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

from cards.models import Decision, DecisionCard, KeyClaim
from orchestration import card_review, jev


def _card(refs):
    now = datetime(2026, 6, 25, tzinfo=UTC)
    return DecisionCard(
        card_id="review_card", corp_code="00126380", ticker="005930",
        generated_at=now, as_of=now, expires_at=now + timedelta(days=30),
        decision=Decision(stance="HOLD", conviction=0.5, horizon_days=30),
        key_claims=[KeyClaim(id="claim", text="Source A establishes growth.",
                            evidence_refs=refs, weight="MEDIUM", confidence=0.8)],
        assumptions=["Evidence remains current"], body_md="Original card",
    )


def _bundle():
    numeric = SimpleNamespace(model_dump=lambda **kwargs: {"rows": []})
    return SimpleNamespace(
        filings=[SimpleNamespace(rcept_no="20260601000001", body_md="Source A only",
                                 filed_at=datetime(2026, 6, 1, tzinfo=UTC))],
        hybrid_bodies=[SimpleNamespace(ref="n2", body="Source B only", source_type="news")],
        hybrid_hits=[], ohlcv=numeric, flow=numeric, peers=[], portfolio_note=None,
        ticker="005930", as_of="2026-06-25",
    )


@pytest.fixture
def audit(monkeypatch):
    monkeypatch.setenv("JEV_MODE", "shadow")
    records = []
    monkeypatch.setattr(jev, "find_completed", lambda *args, **kwargs: None)
    monkeypatch.setattr(jev, "insert_review", lambda engine, row: records.append(row))
    return records


def _backend(choice="supports"):
    calls = []

    def invoke(**kwargs):
        calls.append(kwargs)
        return {"answers": {"relation": {
            "choice": choice, "confidence": 0.99,
            "probabilities": {option: float(option == choice)
                              for option in kwargs["questions"]["relation"]["criteria"]},
        }}}

    return invoke, calls


def test_each_claim_citation_is_reviewed_separately_and_card_unchanged(audit):
    card = _card(["dart:20260601000001", "news:n2", "news:n2"])
    before = card.model_dump(mode="json")
    backend, calls = _backend()
    report = card_review.review_card(object(), card, bundle=_bundle(), backend=backend)
    assert report["status"] == "completed"
    assert len(calls) == len(audit) == 2
    assert calls[0]["state"]["cited_source"]["body"] == "Source A only"
    assert "Source B only" not in str(calls[0]["state"])
    assert calls[1]["state"]["cited_source"]["body"] == "Source B only"
    assert "Source A only" not in str(calls[1]["state"])
    assert card.model_dump(mode="json") == before


@pytest.mark.parametrize("ref", ["20260601000001", "dart:20260601000001", "filing:20260601000001"])
def test_filing_reference_aliases_use_same_bundle_source(audit, ref):
    backend, calls = _backend()
    report = card_review.review_card(object(), _card([ref]), bundle=_bundle(), backend=backend)
    assert report["status"] == "completed"
    assert calls[0]["state"]["cited_source"]["body"] == "Source A only"


@pytest.mark.parametrize("refs", [[], ["news:missing"]])
def test_missing_references_are_audited_without_api(audit, refs):
    backend, calls = _backend()
    report = card_review.review_card(object(), _card(refs), bundle=_bundle(), backend=backend)
    assert not calls
    assert report["requires_review"]
    assert audit[0]["error_code"] == "missing_source"


@pytest.mark.parametrize("ref", ["ohlcv:005930", "flow:005930", "peers:005930"])
def test_stored_numeric_references_do_not_lookup_current_market_data(audit, ref):
    engine = MagicMock()
    backend, calls = _backend()
    report = card_review.review_card(engine, _card([ref]), backend=backend)
    engine.connect.return_value.__enter__.return_value.execute.assert_not_called()
    assert not calls
    assert report["requires_review"]
    assert audit[0]["error_code"] == "missing_source"


def test_unsupported_adapter_result_requires_review(audit):
    backend, calls = _backend("unsupported")
    report = card_review.review_card(object(), _card(["dart:20260601000001"]),
                                   bundle=_bundle(), backend=backend)
    assert len(calls) == 1
    assert report["requires_review"]
    assert report["items"][0]["answers"]["relation"]["choice"] == "unsupported"


def test_off_touches_neither_database_nor_backend(monkeypatch):
    monkeypatch.setenv("JEV_MODE", "off")
    engine, backend = MagicMock(), MagicMock()
    report = card_review.review_card(engine, _card(["news:123"]), backend=backend)
    assert report["status"] == "disabled"
    assert not engine.mock_calls
    backend.assert_not_called()


@pytest.mark.parametrize("ref,date_column", [
    ("20260601000001", "filed_at"), ("dart:20260601000001", "filed_at"),
    ("news:123", "published_at"),
])
def test_stored_source_query_enforces_card_cutoff(ref, date_column):
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.mappings.return_value.first.return_value = None
    card = _card([ref])
    assert card_review.stored_source(engine, ref, card) is None
    statement, params = connection.execute.call_args.args
    assert f"{date_column}<=:as_of" in str(statement)
    assert params["as_of"] == card.as_of


def test_pipeline_wrapper_preserves_saved_card_on_audit_failure(monkeypatch, caplog):
    def fail(*args, **kwargs):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(card_review, "review_card", fail)
    card = _card(["news:123"])
    before = card.model_dump()
    card_review.review_generated_card(object(), card, _bundle())
    assert card.model_dump() == before
    assert "Jev shadow review failed" in caplog.text


def test_stored_news_cutoff_excludes_future_and_accepts_boundary(pg_clean):
    card = _card([])
    with pg_clean.begin() as connection:
        for suffix, published_at in (("1", card.as_of),
                                     ("2", card.as_of + timedelta(seconds=1))):
            connection.execute(text(
                "INSERT INTO news (url_hash,url,outlet,published_at,title,content_hash,body_md) "
                "VALUES (:hash,:url,'test',:published,'Headline',:hash,'Cited body')"
            ), {"hash": suffix * 64, "url": f"https://example.com/{suffix}",
                "published": published_at})
    assert card_review.stored_source(pg_clean, "news:" + "1" * 64, card)["body"] == "Cited body"
    assert card_review.stored_source(pg_clean, "news:" + "2" * 64, card) is None


def test_hybrid_snippet_cannot_overwrite_more_complete_news_body():
    bundle = _bundle()
    bundle.hybrid_hits = [SimpleNamespace(source_type="news", id_or_path="n2", snippet="Snippet")]
    assert card_review.bundle_sources(bundle)["news:n2"]["body"] == "Source B only"


def test_no_claims_is_audited_without_backend(audit):
    card = _card([])
    card.key_claims = []
    backend, calls = _backend()
    report = card_review.review_card(object(), card, bundle=_bundle(), backend=backend)
    assert not calls
    assert report["requires_review"]
    assert audit[0]["error_code"] == "no_claims"
