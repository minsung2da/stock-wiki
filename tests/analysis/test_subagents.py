"""D-01 sub-agent seam tests — quota-free (patched ``_spawn_claude`` / fake backend).

No real ``claude`` process is ever spawned here (the single subprocess seam is
patched, exactly like ``tests/test_dart_fetcher_retry.py`` patches ``_http_get``).
Locks the D-01 mechanics the runner depends on:

- the RESEARCH-locked argv flags (``--output-format json`` / ``--json-schema`` /
  ``--strict-mcp-config``) are present and ``--bare`` is NEVER present;
- evidence rides **stdin**, never argv (T-04-13);
- the parsed ``structured_output`` is read, not the ``result`` string;
- an ``is_error`` envelope raises ``SubAgentError``; a retryable category triggers
  exactly ONE retry then raises; a non-zero exit is permanent;
- Bull/Bear run in parallel over the SAME bundle, blind to each other; the Judge
  receives both outputs (SC#2b/c).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from analysis import subagents
from analysis.subagents import (
    ClaudeCliBackend,
    RoleResult,
    SubAgentError,
    SubAgentRetryableError,
    run_bull_bear,
)

# A minimal well-formed success envelope (RESEARCH §3 keys). ``structured_output`` and
# ``result`` deliberately DIFFER so a test can prove the object (not the string) wins.
_OK_ENV: dict = {
    "is_error": False,
    "structured_output": {"stance_support": "HOLD", "claims": [], "numeric_facts": []},
    "result": '{"stance_support": "WRONG_FROM_RESULT_STRING"}',
    "total_cost_usd": 0.14,
    "duration_ms": 1234,
    "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 50},
    "modelUsage": {"claude-sonnet-4-6": {"costUSD": 0.14}},
}


class _SpyClaude:
    """Stand-in for ``subagents._spawn_claude``: record argv/stdin, return a canned
    ``(returncode, stdout, stderr)`` — never spawns a subprocess."""

    def __init__(self, envelope: dict, *, returncode: int = 0, stderr: bytes = b"") -> None:
        self.env_bytes = json.dumps(envelope).encode("utf-8")
        self.returncode = returncode
        self.stderr = stderr
        self.argvs: list[list[str]] = []
        self.stdins: list[bytes] = []
        self.calls = 0

    async def __call__(
        self, argv: list[str], stdin_bytes: bytes, timeout_s: float
    ) -> tuple[int, bytes, bytes]:
        self.calls += 1
        self.argvs.append(list(argv))
        self.stdins.append(stdin_bytes)
        return self.returncode, self.env_bytes, self.stderr


def _run_bull(spy: _SpyClaude, evidence: str = "EVIDENCE BODY xyz") -> RoleResult:
    backend = ClaudeCliBackend()
    return asyncio.run(
        backend.run("bull", "role instruction", "SYSTEM PROMPT", {"type": "object"}, evidence)
    )


# --------------------------------------------------------------------------- #
# argv shape + stdin delivery (T-04-13, D-01)
# --------------------------------------------------------------------------- #
def test_argv_has_locked_flags_and_never_bare(monkeypatch) -> None:
    spy = _SpyClaude(_OK_ENV)
    monkeypatch.setattr(subagents, "_spawn_claude", spy)

    _run_bull(spy)
    argv = spy.argvs[0]

    assert "--strict-mcp-config" in argv
    assert "--json-schema" in argv
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    assert "--append-system-prompt" in argv
    # The Max-only Veto flag must NEVER appear (would force ANTHROPIC_API_KEY).
    assert "--bare" not in argv
    # First two tokens are the non-interactive headless invocation.
    assert argv[0] == "claude"
    assert argv[1] == "-p"


def test_evidence_rides_stdin_never_argv(monkeypatch) -> None:
    spy = _SpyClaude(_OK_ENV)
    monkeypatch.setattr(subagents, "_spawn_claude", spy)

    _run_bull(spy, evidence="UNTRUSTED EVIDENCE 42.5조원")

    # Evidence body is on stdin, UTF-8 encoded ...
    assert spy.stdins[0] == "UNTRUSTED EVIDENCE 42.5조원".encode()
    # ... and never interpolated into any argv token (injection / 32K limit).
    assert all("UNTRUSTED EVIDENCE" not in tok for tok in spy.argvs[0])


def test_json_schema_is_inline_json_string(monkeypatch) -> None:
    spy = _SpyClaude(_OK_ENV)
    monkeypatch.setattr(subagents, "_spawn_claude", spy)

    backend = ClaudeCliBackend()
    schema = {"type": "object", "required": ["stance_support"]}
    asyncio.run(backend.run("bull", "instr", "sys", schema, "ev"))

    argv = spy.argvs[0]
    inline = argv[argv.index("--json-schema") + 1]
    # It is an inline JSON STRING (not a file path) — round-trips back to the schema.
    assert json.loads(inline) == schema


# --------------------------------------------------------------------------- #
# envelope reading (structured_output, not result) + cost subset
# --------------------------------------------------------------------------- #
def test_reads_structured_output_not_result(monkeypatch) -> None:
    spy = _SpyClaude(_OK_ENV)
    monkeypatch.setattr(subagents, "_spawn_claude", spy)

    result = _run_bull(spy)
    assert isinstance(result, RoleResult)
    assert result.role == "bull"
    assert result.data == _OK_ENV["structured_output"]
    assert result.data["stance_support"] == "HOLD"  # NOT "WRONG_FROM_RESULT_STRING"


def test_roleresult_cost_carries_envelope_subset(monkeypatch) -> None:
    spy = _SpyClaude(_OK_ENV)
    monkeypatch.setattr(subagents, "_spawn_claude", spy)

    result = _run_bull(spy)
    assert result.cost["total_cost_usd"] == 0.14
    assert result.cost["duration_ms"] == 1234
    assert result.cost["input_tokens"] == 100
    assert result.cost["output_tokens"] == 20
    assert result.cost["cache_read_input_tokens"] == 50
    assert result.cost["model"] == "claude-sonnet-4-6"


# --------------------------------------------------------------------------- #
# error classification: permanent vs retryable-one-retry vs non-zero exit
# --------------------------------------------------------------------------- #
def test_is_error_authentication_is_permanent_no_retry(monkeypatch) -> None:
    env = {"is_error": True, "error": "authentication_failed", "result": "not logged in"}
    spy = _SpyClaude(env)
    monkeypatch.setattr(subagents, "_spawn_claude", spy)

    with pytest.raises(SubAgentError) as exc:
        _run_bull(spy)
    # Permanent (auth) — NOT a retryable subtype, and tried exactly once.
    assert not isinstance(exc.value, SubAgentRetryableError)
    assert spy.calls == 1
    assert exc.value.role == "bull"


def test_is_error_overloaded_retries_exactly_once_then_raises(monkeypatch) -> None:
    env = {"is_error": True, "error": "overloaded", "result": "overloaded_error"}
    spy = _SpyClaude(env)
    monkeypatch.setattr(subagents, "_spawn_claude", spy)

    with pytest.raises(SubAgentRetryableError):
        _run_bull(spy)
    assert spy.calls == 2  # one initial + exactly one retry, then fail loudly


def test_rate_limit_is_retryable(monkeypatch) -> None:
    env = {"is_error": True, "subtype": "rate_limit"}
    spy = _SpyClaude(env)
    monkeypatch.setattr(subagents, "_spawn_claude", spy)

    with pytest.raises(SubAgentRetryableError):
        _run_bull(spy)
    assert spy.calls == 2


def test_non_zero_exit_is_permanent(monkeypatch) -> None:
    spy = _SpyClaude(_OK_ENV, returncode=1, stderr=b"claude: fatal")
    monkeypatch.setattr(subagents, "_spawn_claude", spy)

    with pytest.raises(SubAgentError) as exc:
        _run_bull(spy)
    assert not isinstance(exc.value, SubAgentRetryableError)
    assert exc.value.category == "non_zero_exit"
    assert spy.calls == 1


def test_bad_envelope_is_permanent(monkeypatch) -> None:
    async def _garbage(argv, stdin_bytes, timeout_s):
        return 0, b"not json at all", b""

    monkeypatch.setattr(subagents, "_spawn_claude", _garbage)
    backend = ClaudeCliBackend()
    with pytest.raises(SubAgentError) as exc:
        asyncio.run(backend.run("bull", "i", "s", {}, "ev"))
    assert exc.value.category == "bad_envelope"


# --------------------------------------------------------------------------- #
# SC#2b/c — parallel, blind Bull/Bear; Judge sees both (fake backend, no subprocess)
# --------------------------------------------------------------------------- #
def test_bull_bear_parallel_blind_and_judge_sees_both(fake_debate_backend) -> None:
    backend = fake_debate_backend
    prompts = {"bull": "BULL_SYS", "bear": "BEAR_SYS", "judge": "JUDGE_SYS"}
    schemas = {"bull": {}, "bear": {}, "judge": {}}
    bundle = "SHARED_EVIDENCE_BUNDLE"

    async def _drive():
        bull, bear = await run_bull_bear(
            backend,
            instruction="analyze",
            bundle_stdin=bundle,
            prompts=prompts,
            schemas=schemas,
        )
        judge_stdin = (
            bundle + "\n\n" + json.dumps(bull.data) + "\n\n" + json.dumps(bear.data)
        )
        judge = await backend.run(
            "judge", "synthesize", prompts["judge"], schemas["judge"], judge_stdin
        )
        return bull, bear, judge

    bull, bear, judge = asyncio.run(_drive())

    roles = [c.role for c in backend.calls]
    assert roles == ["bull", "bear", "judge"]

    bull_call = next(c for c in backend.calls if c.role == "bull")
    bear_call = next(c for c in backend.calls if c.role == "bear")
    judge_call = next(c for c in backend.calls if c.role == "judge")

    # Bull and Bear each received the IDENTICAL bundle ...
    assert bull_call.evidence_stdin == bundle
    assert bear_call.evidence_stdin == bundle
    # ... and are BLIND: neither carries the other's output on its stdin.
    assert json.dumps(bear.data) not in bull_call.evidence_stdin
    assert json.dumps(bull.data) not in bear_call.evidence_stdin

    # The Judge (and ONLY the Judge) sees both sub-agent outputs.
    assert bundle in judge_call.evidence_stdin
    assert json.dumps(bull.data) in judge_call.evidence_stdin
    assert json.dumps(bear.data) in judge_call.evidence_stdin
    assert judge.data["decision"]["stance"] == "HOLD"


def test_run_bull_bear_calls_only_two_roles(fake_debate_backend) -> None:
    backend = fake_debate_backend
    asyncio.run(
        run_bull_bear(
            backend,
            instruction="analyze",
            bundle_stdin="BUNDLE",
            prompts={"bull": "b", "bear": "r"},
            schemas={"bull": {}, "bear": {}},
        )
    )
    # The parallel step runs Bull + Bear only — the Judge is a later, separate call.
    assert sorted(c.role for c in backend.calls) == ["bear", "bull"]
