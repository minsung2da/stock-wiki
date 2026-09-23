"""Bounded Choice-only Jev advice with a durable audit trail, never trading authority."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy.engine import Engine

from db.jev_reviews import find_completed, insert_review

PROMPT_VERSION = "jev-shadow-v1"
MAX_INPUT_CHARS = 100_000
_log = logging.getLogger(__name__)


class ReviewBackend(Protocol):
    def __call__(
        self, *, state: dict[str, Any], questions: dict[str, dict[str, Any]], model: str
    ) -> dict[str, Any]: ...


def _sdk_backend(
    *, state: dict[str, Any], questions: dict[str, dict[str, Any]], model: str
) -> dict[str, Any]:
    from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient, TypeSafeError

    with TypeSafeClient(model=model, timeout=30.0, retry=RetryPolicy(max_retries=1)) as client:
        response = client.system_one(
            state=state,
            questions={
                name: Choice(instructions=q.get("instructions"), criteria=q["criteria"])
                for name, q in questions.items()
            },
        )
        result: dict[str, Any] = response.model_dump(mode="json")
        try:
            result["request_id"] = response.request_id
        except TypeSafeError:
            result["request_id"] = None
        return result


def _probability(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid_probability")
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError("invalid_probability")
    return number


def _answers(raw: Any, questions: dict[str, dict[str, Any]], threshold: float) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != set(questions):
        raise ValueError("invalid_answer_keys")
    result = {}
    for name, question in questions.items():
        answer = raw[name]
        options = set(question["criteria"])
        if not isinstance(answer, dict) or answer.get("choice") not in options:
            raise ValueError("invalid_choice")
        probabilities = answer.get("probabilities")
        if not isinstance(probabilities, dict) or set(probabilities) != options:
            raise ValueError("invalid_probability_keys")
        probabilities = {key: _probability(value) for key, value in probabilities.items()}
        confidence = _probability(answer.get("confidence"))
        if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=0.001):
            raise ValueError("invalid_probability_sum")
        if probabilities[answer["choice"]] < max(probabilities.values()):
            raise ValueError("choice_not_maximum")
        result[name] = {
            "choice": answer["choice"],
            "probabilities": probabilities,
            "confidence": confidence,
            "requires_review": confidence <= threshold
            or answer["choice"] in {"contradicts", "unsupported", "insufficient"},
        }
    return result


def review_choices(
    engine: Engine,
    *,
    task: str,
    subject_id: str,
    state: dict[str, Any],
    questions: dict[str, dict[str, Any]],
    backend: ReviewBackend | None = None,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    """Return advisory results; errors must never interrupt the existing pipeline."""
    mode = os.getenv("JEV_MODE", "off").strip().lower()
    model = os.getenv("TYPESAFE_DEFAULT_MODEL", "jev-1.13.0").strip() or "jev-1.13.0"
    report: dict[str, Any] = {
        "status": "disabled",
        "mode": mode,
        "model": model,
        "input_hash": None,
        "answers": {},
        "error_code": None,
        "review_id": None,
        "cached": False,
        "request_id": None,
        "usage": {},
        "requires_review": True,
    }
    if mode == "off":
        return report
    threshold = 0.8
    payload: dict[str, Any] = {}
    try:
        threshold = _probability(float(os.getenv("JEV_CONFIDENCE_THRESHOLD", "0.8")))
        if mode != "shadow":
            report["mode"] = "off"
            raise ValueError("invalid_mode")
        if not isinstance(state, dict) or not isinstance(questions, dict):
            raise ValueError("invalid_input")
        payload = {
            "state": state,
            "questions": questions,
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "threshold": threshold,
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        report["input_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        if len(encoded) > MAX_INPUT_CHARS:
            payload = {"omitted": "input_too_large", "input_chars": len(encoded)}
            raise ValueError("input_too_large")
        if unavailable_reason is not None:
            raise ValueError(
                unavailable_reason
                if unavailable_reason in {"missing_source", "no_claims"}
                else "source_unavailable"
            )
        if not questions or any(
            not isinstance(name, str)
            or not name
            or not isinstance(q, dict)
            or q.get("type", "choice") != "choice"
            or not isinstance(q.get("criteria"), dict)
            or not 2 <= len(q["criteria"]) <= 255
            or any(not isinstance(option, str) or not option for option in q["criteria"])
            for name, q in questions.items()
        ):
            raise ValueError("invalid_questions")
        try:
            cached = find_completed(
                engine, task=task, subject_id=subject_id, input_hash=report["input_hash"]
            )
        except Exception:
            _log.error("jev_audit_read_failed", extra={"task": task})
            raise ValueError("audit_unavailable") from None
        if cached is not None:
            cached["cached"] = True
            return cached
        if backend is None and not os.getenv("TYPESAFE_API_KEY", "").strip():
            raise ValueError("missing_key")
        try:
            raw = (backend or _sdk_backend)(state=state, questions=questions, model=model)
        except Exception:
            raise ValueError("api_error") from None
        try:
            report["answers"] = _answers(raw.get("answers"), questions, threshold)
            returned_model = raw.get("model", model)
            if (
                not isinstance(returned_model, str)
                or not returned_model
                or len(returned_model) > 200
            ):
                raise ValueError("model")
            report["model"] = returned_model
            usage = raw.get("usage") or {}
            if not isinstance(usage, dict):
                raise ValueError("usage")
            report["usage"] = {
                key: value
                for key, value in usage.items()
                if key in {"input_tokens", "output_tokens"}
                and isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
            }
            request_id = raw.get("request_id")
            if request_id is not None and (
                not isinstance(request_id, str) or len(request_id) > 200
            ):
                raise ValueError("request_id")
            report["request_id"] = request_id
        except (ValueError, TypeError, AttributeError):
            report["answers"] = {}
            raise ValueError("malformed_response") from None
        report["status"] = "completed"
        report["requires_review"] = any(a["requires_review"] for a in report["answers"].values())
    except (ValueError, TypeError) as exc:
        allowed = {
            "invalid_mode",
            "input_too_large",
            "invalid_questions",
            "missing_key",
            "api_error",
            "malformed_response",
            "audit_unavailable",
            "missing_source",
            "no_claims",
            "source_unavailable",
        }
        report["status"] = "error"
        report["error_code"] = (
            exc.args[0] if exc.args and exc.args[0] in allowed else "invalid_input"
        )
        if report["input_hash"] is None:
            payload = {"omitted": "invalid_input"}
            report["input_hash"] = hashlib.sha256(b"invalid_input").hexdigest()
    report["review_id"] = str(uuid4())
    report["prompt_version"] = PROMPT_VERSION
    report["threshold"] = threshold
    try:
        insert_review(
            engine,
            {
                "review_id": report["review_id"],
                "task": task,
                "subject_id": subject_id,
                "input_hash": report["input_hash"],
                "model": report["model"],
                "prompt_version": PROMPT_VERSION,
                "mode": report["mode"],
                "status": report["status"],
                "threshold": threshold,
                "input_payload": payload,
                "result_payload": report,
                "request_id": report["request_id"],
                "usage": report["usage"],
                "error_code": report["error_code"],
                "created_at": datetime.now(UTC),
            },
        )
    except Exception:
        _log.error("jev_audit_write_failed", extra={"task": task})
        report.update(
            status="error", error_code="audit_unavailable", review_id=None, requires_review=True
        )
    return report
