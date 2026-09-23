"""Deterministic adapter contract tests: no network and no production database."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from db.jev_reviews import jev_reviews, metadata
from orchestration import jev

QUESTIONS = {
    "relation": {
        "instructions": "Compare the claim with the cited source.",
        "criteria": {"supports": "Supported", "insufficient": "Not enough"},
    }
}
STATE = {"claim": "Revenue grew", "source_id": "filing:20260901001", "source": "Revenue grew"}


class FakeBackend:
    def __init__(self):
        self.calls = []
        self.response = {
            "answers": {
                "relation": {
                    "choice": "supports",
                    "confidence": 0.9,
                    "probabilities": {"supports": 0.95, "insufficient": 0.05},
                }
            },
            "request_id": "request-test-1",
            "usage": {"input_tokens": 30, "output_tokens": 10},
        }

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return deepcopy(self.response)


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setenv("JEV_MODE", "shadow")
    monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "jev-1.13.0")
    monkeypatch.setenv("JEV_CONFIDENCE_THRESHOLD", "0.8")
    instance = sa.create_engine("sqlite://")
    metadata.create_all(instance)
    yield instance
    instance.dispose()


def review(engine, backend, **kwargs):
    return jev.review_choices(
        engine,
        task="card_claim",
        subject_id="card-1/claim-0",
        state=kwargs.pop("state", STATE),
        questions=kwargs.pop("questions", QUESTIONS),
        backend=backend,
        **kwargs,
    )


def rows(engine):
    with engine.connect() as conn:
        return conn.execute(sa.select(jev_reviews)).mappings().all()


def test_completed_review_audits_full_source_and_caches(engine):
    backend = FakeBackend()
    result = review(engine, backend)
    assert result["status"] == "completed" and not result["requires_review"]
    assert result["answers"]["relation"]["confidence"] == 0.9  # not selected probability .95
    audit = rows(engine)[0]
    assert audit["input_payload"]["state"] == STATE
    assert audit["result_payload"] == result
    assert audit["request_id"] == "request-test-1"
    assert audit["usage"] == {"input_tokens": 30, "output_tokens": 10}
    second = review(engine, backend)
    assert second["cached"] and second["review_id"] == result["review_id"]
    assert len(backend.calls) == len(rows(engine)) == 1


@pytest.mark.parametrize("change", ["state", "question", "model", "threshold", "version"])
def test_cache_invalidates_on_relevant_change(engine, monkeypatch, change):
    backend = FakeBackend()
    old = review(engine, backend)
    kwargs = {}
    if change == "state":
        kwargs["state"] = {**STATE, "source": "Revenue fell"}
    elif change == "question":
        kwargs["questions"] = deepcopy(QUESTIONS)
        kwargs["questions"]["relation"]["instructions"] = "Is the claim fully supported?"
    elif change == "model":
        monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "jev-test-model")
    elif change == "threshold":
        monkeypatch.setenv("JEV_CONFIDENCE_THRESHOLD", "0.95")
    else:
        monkeypatch.setattr(jev, "PROMPT_VERSION", "test-v2")
    new = review(engine, backend, **kwargs)
    assert len(backend.calls) == 2 and new["input_hash"] != old["input_hash"]


@pytest.mark.parametrize("confidence", [0.0, 0.8, 0.80001])
def test_threshold_boundary(engine, confidence):
    backend = FakeBackend()
    backend.response["answers"]["relation"]["confidence"] = confidence
    result = review(engine, backend)
    assert result["answers"]["relation"]["requires_review"] is (confidence <= 0.8)


@pytest.mark.parametrize("choice", ["insufficient", "unsupported", "contradicts"])
def test_adverse_choice_requires_review_even_at_high_confidence(engine, choice):
    backend = FakeBackend()
    backend.response["answers"]["relation"] = {
        "choice": choice,
        "confidence": 1.0,
        "probabilities": {"supports": 0.0, choice: 1.0},
    }
    questions = {"relation": {"criteria": {"supports": "yes", choice: "needs review"}}}
    assert review(engine, backend, questions=questions)["requires_review"]


@pytest.mark.parametrize(
    "bad",
    [
        {"choice": "invented"},
        {"confidence": float("nan")},
        {"confidence": -0.1},
        {"confidence": True},
        {"confidence": "0.9"},
        {"probabilities": {"supports": 1.0}},
        {"probabilities": {"supports": 0.5, "insufficient": 0.1}},
        {"probabilities": {"supports": -0.1, "insufficient": 1.1}},
        {"probabilities": {"supports": 0.1, "insufficient": 0.9}},
    ],
)
def test_malformed_response_is_audited_and_never_cached(engine, bad):
    backend = FakeBackend()
    backend.response["answers"]["relation"].update(bad)
    assert review(engine, backend)["error_code"] == "malformed_response"
    assert review(engine, backend)["error_code"] == "malformed_response"
    assert len(backend.calls) == len(rows(engine)) == 2
    assert all(row["result_payload"]["answers"] == {} for row in rows(engine))


def test_network_error_does_not_leak_exception_or_keys(engine):
    def broken(**kwargs):
        raise RuntimeError("Authorization: secret-key-123")

    result = review(engine, broken)
    assert result["error_code"] == "api_error"
    assert "secret-key-123" not in str(rows(engine))


def test_missing_key_audited(engine, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert review(engine, None)["error_code"] == "missing_key"
    assert len(rows(engine)) == 1


def test_off_has_no_api_or_database_side_effect(engine, monkeypatch):
    monkeypatch.delenv("JEV_MODE")
    backend = FakeBackend()
    assert review(engine, backend)["status"] == "disabled"
    assert backend.calls == [] and rows(engine) == []


def test_oversized_input_is_not_truncated_and_sent(engine):
    backend = FakeBackend()
    result = review(engine, backend, state={"source": "x" * jev.MAX_INPUT_CHARS})
    assert result["error_code"] == "input_too_large" and backend.calls == []
    assert rows(engine)[0]["input_payload"]["omitted"] == "input_too_large"


def test_missing_source_does_not_reuse_completed_result(engine):
    backend = FakeBackend()
    review(engine, backend)
    result = review(engine, backend, unavailable_reason="missing_source")
    assert result["error_code"] == "missing_source"
    assert len(backend.calls) == 1 and len(rows(engine)) == 2


def test_database_failure_is_visible_and_skips_api(engine, caplog):
    metadata.drop_all(engine)
    backend = FakeBackend()
    result = review(engine, backend)
    assert result["status"] == "error" and result["error_code"] == "audit_unavailable"
    assert result["review_id"] is None and backend.calls == []
    assert "jev_audit_read_failed" in caplog.text and "jev_audit_write_failed" in caplog.text


def test_sdk_uses_bounded_transport_and_choice_questions(monkeypatch):
    import sys

    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def system_one(self, **kwargs):
            captured["call"] = kwargs
            return SimpleNamespace(
                model_dump=lambda **_: FakeBackend().response, request_id="sdk-request-1"
            )

    monkeypatch.setitem(
        sys.modules,
        "typesafe_sdk",
        SimpleNamespace(
            TypeSafeClient=Client,
            RetryPolicy=lambda **kwargs: kwargs,
            Choice=lambda **kwargs: kwargs,
            TypeSafeError=RuntimeError,
        ),
    )
    result = jev._sdk_backend(state=STATE, questions=QUESTIONS, model="jev-test")
    assert captured["timeout"] == 30.0 and captured["retry"] == {"max_retries": 1}
    assert captured["model"] == "jev-test" and captured["call"]["state"] == STATE
    assert (
        captured["call"]["questions"]["relation"]["criteria"] == QUESTIONS["relation"]["criteria"]
    )
    assert result["request_id"] == "sdk-request-1"
