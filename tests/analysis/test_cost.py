"""SC#7 cost/time capture tests (pure-function, no subprocess, no DB).

Locks the envelope-subset extraction + the structured-stderr sink:

- ``capture_cost`` extracts ``total_cost_usd`` / ``duration_ms`` / token counts / model
  from the live-verified ``claude -p`` JSON envelope, and defensively tolerates a
  partial / malformed envelope (missing keys, non-dict ``usage``, non-numeric values);
- ``emit_cost`` logs exactly ONE structured line (assertable via caplog) and NEVER
  raises, even on an all-``None`` StageCost;
- ``cost.py`` never calls ``record_collector_run`` (its 7-source CHECK excludes
  analysis — RESEARCH §6; structured stderr alone is the SC#7 contract).
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from analysis import cost as cost_mod
from analysis.cost import StageCost, capture_cost, emit_cost

# The live-verified envelope subset (RESEARCH §3): a real "pong" call shape with
# cache reuse across sequential sub-agent invocations.
_FULL_ENV: dict = {
    "is_error": False,
    "total_cost_usd": 0.17,
    "duration_ms": 1523,
    "usage": {
        "input_tokens": 27372,
        "output_tokens": 42,
        "cache_read_input_tokens": 19967,
        "cache_creation_input_tokens": 22506,
    },
    "modelUsage": {"claude-sonnet-4-6": {"inputTokens": 27372, "costUSD": 0.17}},
}


def test_capture_cost_extracts_envelope_subset() -> None:
    sc = capture_cost("bull", _FULL_ENV)
    assert isinstance(sc, StageCost)
    assert sc.role == "bull"
    assert sc.total_cost_usd == 0.17
    assert sc.duration_ms == 1523
    assert sc.input_tokens == 27372
    assert sc.output_tokens == 42
    assert sc.cache_read_input_tokens == 19967
    assert sc.model == "claude-sonnet-4-6"


def test_capture_cost_tolerates_empty_envelope() -> None:
    sc = capture_cost("bear", {})
    assert sc.role == "bear"
    assert sc.total_cost_usd is None
    assert sc.duration_ms is None
    assert sc.input_tokens is None
    assert sc.output_tokens is None
    assert sc.cache_read_input_tokens is None
    assert sc.model is None


def test_capture_cost_tolerates_malformed_fields() -> None:
    sc = capture_cost(
        "judge",
        {"total_cost_usd": "n/a", "duration_ms": None, "usage": "not-a-dict", "modelUsage": {}},
    )
    assert sc.total_cost_usd is None  # non-numeric string → None
    assert sc.duration_ms is None
    assert sc.input_tokens is None  # usage was not a dict → treated as empty
    assert sc.model is None  # empty modelUsage → None


def test_emit_cost_logs_one_structured_line(caplog) -> None:
    sc = capture_cost("bull", _FULL_ENV)
    with caplog.at_level(logging.INFO, logger="analysis.cost"):
        emit_cost(sc)

    records = [r for r in caplog.records if r.getMessage() == "analysis_stage_cost"]
    assert len(records) == 1
    rec = records[0]
    assert rec.stage == "bull"
    assert rec.total_cost_usd == 0.17
    assert rec.duration_ms == 1523
    assert rec.input_tokens == 27372
    assert rec.cache_read_input_tokens == 19967


def test_emit_cost_never_raises_on_partial_envelope(caplog) -> None:
    sc = capture_cost("bear", {})  # all-None numerics
    with caplog.at_level(logging.INFO, logger="analysis.cost"):
        emit_cost(sc)  # must not raise
    records = [r for r in caplog.records if r.getMessage() == "analysis_stage_cost"]
    assert len(records) == 1
    assert records[0].stage == "bear"
    assert records[0].total_cost_usd is None


def test_cost_does_not_call_record_collector_run() -> None:
    """AST-scan cost.py: it must not reference ``record_collector_run`` (a docstring
    mention is fine — the 7-source CHECK excludes analysis, RESEARCH §6)."""
    tree = ast.parse(Path(cost_mod.__file__).read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(a.name for a in node.names)
    assert "record_collector_run" not in names
    assert "record_collector_run" not in attrs
    assert "record_collector_run" not in imported
