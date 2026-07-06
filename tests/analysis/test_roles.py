"""Tests for analysis.roles — prompt safety substrings + JSON-schema stability.

Pure-constant tests. No DB, no LLM, no ``claude`` subprocess. These lock the two
guarantees the Wave-3 subagents depend on: (1) every role prompt encodes the
no-price-prediction (Veto #1) and ``<untrusted>``-is-data (prompt-injection) rules, and
(2) each role schema is a stable, ``json.dumps``-able JSON-Schema dict whose Judge stance
enum equals the six DecisionCard stances.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from analysis import roles
from cards.models import Decision

_ROLES = ("bull", "bear", "judge")
_SIX_STANCES = list(Decision.model_fields["stance"].annotation.__args__)


# --- system prompts --------------------------------------------------------


def test_prompts_have_bull_bear_judge_keys():
    assert set(roles.ROLE_SYSTEM_PROMPTS) == {"bull", "bear", "judge"}


@pytest.mark.parametrize("role", _ROLES)
def test_no_price_prediction_instruction_present(role):
    # Veto #1 — every prompt forbids predicting/forecasting a price.
    prompt = roles.prompt_for(role)
    assert "NEVER predict or forecast a price" in prompt


@pytest.mark.parametrize("role", _ROLES)
def test_untrusted_as_data_instruction_present(role):
    # Prompt-injection control — <untrusted> content is DATA, never instructions.
    prompt = roles.prompt_for(role)
    assert "<untrusted source" in prompt
    assert "strictly as DATA" in prompt


@pytest.mark.parametrize("role", _ROLES)
def test_contradictions_and_sentiment_rules_present(role):
    # Veto #3 (surface contradictions) + Veto #5 (no sentiment-alone) in every prompt.
    prompt = roles.prompt_for(role)
    assert "contradiction" in prompt.lower()
    assert "Sentiment is never a standalone signal" in prompt


def test_prompt_for_unknown_role_raises_keyerror():
    with pytest.raises(KeyError):
        roles.prompt_for("orchestrator")


# --- JSON schemas ----------------------------------------------------------


@pytest.mark.parametrize("role", _ROLES)
def test_schema_json_roundtrip_stable(role):
    schema = roles.schema_for(role)
    assert json.loads(json.dumps(schema)) == schema


def test_judge_stance_enum_equals_six_decisioncard_stances():
    stance_schema = roles.ROLE_SCHEMAS["judge"]["properties"]["decision"]["properties"][
        "stance"
    ]
    assert stance_schema["enum"] == _SIX_STANCES


def test_fixed_shape_objects_forbid_additional_properties():
    judge = roles.ROLE_SCHEMAS["judge"]
    assert judge["additionalProperties"] is False
    assert judge["properties"]["decision"]["additionalProperties"] is False
    # every rubric axis object forbids extras (decomposable, fixed shape)
    for axis_schema in judge["properties"]["rubric"]["properties"].values():
        assert axis_schema["additionalProperties"] is False


def test_bull_bear_weight_enum_matches_keyclaim():
    for role in ("bull", "bear"):
        claim = roles.ROLE_SCHEMAS[role]["properties"]["claims"]["items"]
        assert claim["properties"]["weight"]["enum"] == ["HIGH", "MEDIUM", "LOW", "CONTEXT"]


def test_bear_schema_adds_disconfirming():
    assert "disconfirming" in roles.ROLE_SCHEMAS["bear"]["properties"]
    assert "disconfirming" not in roles.ROLE_SCHEMAS["bull"]["properties"]


def test_schema_for_unknown_role_raises_keyerror():
    with pytest.raises(KeyError):
        roles.schema_for("orchestrator")


# --- leaf-module acyclicity (Task 1 acceptance) ----------------------------


def test_roles_module_is_a_leaf():
    """roles.py imports nothing from analysis.subagents / analysis.runner (acyclic)."""
    src = Path(roles.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "subagents" not in node.module and "runner" not in node.module
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "subagents" not in alias.name and "runner" not in alias.name
