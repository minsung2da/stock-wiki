"""D-01 sub-agent seam — the ONLY path to a model in the whole system.

The analysis brain reaches Sonnet **only** through the headless ``claude`` CLI
subprocess under Max-subscription OAuth (D-01, Max-only Veto). This module never
imports a cloud-LLM SDK (``anthropic`` / ``openai`` — ``tests/test_import_guard.py``
enforces that in CI), never passes ``--bare`` (which would force
``ANTHROPIC_API_KEY`` and break the Max-only Veto), never uses ``shell=True``, and
never reads or sets ``ANTHROPIC_API_KEY``.

The CLI call is isolated behind a :class:`DebateBackend` protocol so the default
test suite runs a fake and spends **zero Max quota** (deep_work_rules). Only the
opt-in ``@pytest.mark.live`` tier (Plan 04-06) touches the real CLI.

Structure mirrors ``src/collectors/dart/fetcher.py`` 1:1 (the repo's only
retry+error-classification+test-seam module):

- :func:`_spawn_claude` — the single patchable subprocess call (mirror of
  ``fetcher._http_get``); tests ``monkeypatch.setattr`` this one function.
- :class:`SubAgentError` (permanent: auth / non-zero exit / bad envelope) vs
  :class:`SubAgentRetryableError` (retryable: overload / rate-limit / timeout) —
  mirror of ``DartDocumentError`` / ``DartThrottleError`` permanent/retryable split,
  classified from the envelope's ``is_error`` + error category (RESEARCH §4).

Evidence rides **stdin** (``communicate(bundle.encode())``), never argv — the
Windows ~32 KB command-line cap plus shell-injection of untrusted narrative
(T-04-13) forbid interpolating the bundle into the command.

Envelope contract (RESEARCH §Verified CLI Mechanics — live-tested): the structured
result lands in ``structured_output`` (a parsed object), NOT ``result`` (a string).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from analysis.cost import capture_cost, emit_cost

_log = logging.getLogger(__name__)

__all__ = [
    "RoleResult",
    "SubAgentError",
    "SubAgentRetryableError",
    "DebateBackend",
    "ClaudeCliBackend",
    "run_bull_bear",
]

# The CLI binary + default model. ``--model sonnet`` resolves to the current Sonnet
# (``claude-sonnet-4-6`` in the live-verified envelope). ``claude`` must already be on
# PATH and Max-logged-in (no ANTHROPIC_API_KEY).
_CLAUDE_BIN = "claude"
_DEFAULT_MODEL = "sonnet"

# One retry on a retryable category, then fail loudly (RESEARCH §4 — "one retry").
_MAX_ATTEMPTS = 2

# Error categories that are transient and safe to retry once (surfaced in the
# envelope's error/subtype/result text). Everything else — including
# ``authentication_failed`` — is PERMANENT (fail loudly, never mask an auth fault).
_RETRYABLE_TOKENS: tuple[str, ...] = (
    "rate_limit",
    "rate-limit",
    "overload",
    "overloaded",
    "429",
    "529",
)


class RoleResult(BaseModel):
    """One sub-agent's parsed output + the SC#7 cost subset for its call.

    ``data`` is the envelope's ``structured_output`` (parsed object, NOT the
    ``result`` string). ``cost`` is the :class:`~analysis.cost.StageCost` subset as a
    dict (``total_cost_usd`` / ``duration_ms`` / token counts / model).
    """

    model_config = ConfigDict(extra="forbid")

    role: str
    data: dict[str, Any]
    cost: dict[str, Any]


class SubAgentError(RuntimeError):
    """A permanent sub-agent fault — auth failure, non-zero exit, or bad envelope.

    Carries the public ``role`` + error ``category`` + a human detail. Never
    includes the OAuth token (the envelope does not echo it; T-04-14) — do not add
    the raw envelope to the message.
    """

    def __init__(self, role: str, category: str, detail: str) -> None:
        self.role = role
        self.category = category
        super().__init__(detail)


class SubAgentRetryableError(SubAgentError):
    """A retryable sub-agent fault — overload / rate-limit / wall-clock timeout.

    A subclass of :class:`SubAgentError` so a caller that catches the base type
    still catches this, but :meth:`ClaudeCliBackend.run` gates its single retry on
    this exact subtype (mirrors ``DartThrottleError`` ⊂ ``DartDocumentError``).
    """


@runtime_checkable
class DebateBackend(Protocol):
    """The seam the Wave-3 runner orchestrates; the fake and the real CLI both fit.

    ``schema`` + ``system_prompt`` are PARAMETERS (not imported here) so this module
    stays a leaf — the runner wires ``roles.prompt_for`` / ``roles.schema_for`` in.
    """

    async def run(
        self,
        role: str,
        instruction: str,
        system_prompt: str,
        schema: dict,
        evidence_stdin: str,
        *,
        timeout_s: float = 180.0,
    ) -> RoleResult: ...


async def _spawn_claude(
    argv: list[str], stdin_bytes: bytes, timeout_s: float
) -> tuple[int | None, bytes, bytes]:
    """Single ``claude -p`` subprocess call — the patchable test seam.

    Mirrors ``fetcher._http_get``: isolate the raw call so tests patch ONE function.
    Spawns with ``create_subprocess_exec`` (argv list, NO ``shell=True``), pipes the
    evidence bundle through **stdin**, and enforces a wall-clock timeout
    (T-04-15). Returns ``(returncode, stdout, stderr)``; a timeout raises a retryable
    error after killing the child.
    """
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(stdin_bytes), timeout=timeout_s
        )
    except (asyncio.TimeoutError, TimeoutError) as exc:
        proc.kill()
        with contextlib.suppress(Exception):
            await proc.communicate()
        raise SubAgentRetryableError(
            "(spawn)", "timeout", f"claude -p exceeded {timeout_s}s wall-clock"
        ) from exc
    return proc.returncode, out, err


def _error_category(env: dict[str, Any]) -> str:
    """Best-effort extraction of an error category from an ``is_error`` envelope.

    The CLI surfaces the category across a few fields depending on failure mode
    (``authentication_failed`` / ``rate_limit`` / ``overloaded`` …); fall back to the
    ``result`` text. Never returns the raw envelope (no token leakage)."""
    for key in ("error_type", "subtype", "error", "stop_reason"):
        val = env.get(key)
        if isinstance(val, str) and val:
            return val.lower()
    result = env.get("result")
    if isinstance(result, str) and result:
        return result.lower()
    return "unknown"


def _is_retryable_category(category: str) -> bool:
    return any(tok in category for tok in _RETRYABLE_TOKENS)


def _raise_for_envelope(role: str, env: dict[str, Any]) -> None:
    """Raise the correct typed error for an ``is_error: true`` envelope."""
    category = _error_category(env)
    detail = f"claude sub-agent {role!r} returned is_error (category={category})"
    if _is_retryable_category(category):
        raise SubAgentRetryableError(role, category, detail)
    raise SubAgentError(role, category, detail)


class ClaudeCliBackend:
    """Real :class:`DebateBackend` — the headless ``claude`` CLI subprocess (D-01).

    Never spawned by the default test suite (the seam is patched / the fake is used).
    """

    def __init__(self, *, model: str = _DEFAULT_MODEL) -> None:
        self._model = model

    def _build_argv(
        self, instruction: str, system_prompt: str, schema: dict
    ) -> list[str]:
        """The RESEARCH-locked argv. Evidence is NOT here — it rides stdin (T-04-13).

        NEVER ``--bare`` (would force ANTHROPIC_API_KEY → breaks Max-only Veto).
        ``--strict-mcp-config`` suppresses the ``.mcp.json`` auto-spawn (Pitfall 3)."""
        return [
            _CLAUDE_BIN,
            "-p",
            instruction,
            "--output-format",
            "json",
            "--model",
            self._model,
            "--json-schema",
            json.dumps(schema),
            "--strict-mcp-config",
            "--append-system-prompt",
            system_prompt,
        ]

    async def run(
        self,
        role: str,
        instruction: str,
        system_prompt: str,
        schema: dict,
        evidence_stdin: str,
        *,
        timeout_s: float = 180.0,
    ) -> RoleResult:
        """Run one sub-agent role via ``claude -p``; one retry on a retryable fault."""
        argv = self._build_argv(instruction, system_prompt, schema)
        stdin_bytes = evidence_stdin.encode("utf-8")
        last: SubAgentRetryableError | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return await self._run_once(role, argv, stdin_bytes, timeout_s)
            except SubAgentRetryableError as exc:
                last = exc
                _log.warning(
                    "subagent retryable fault role=%s attempt=%d/%d category=%s",
                    role,
                    attempt,
                    _MAX_ATTEMPTS,
                    exc.category,
                )
        assert last is not None  # loop always sets `last` before exhausting
        raise last

    async def _run_once(
        self, role: str, argv: list[str], stdin_bytes: bytes, timeout_s: float
    ) -> RoleResult:
        returncode, out, err = await _spawn_claude(argv, stdin_bytes, timeout_s)
        # Tee the raw stdout bytes to a DEBUG log BEFORE json.loads (debuggability).
        # The envelope never carries the OAuth token (T-04-14), so this is safe.
        _log.debug("subagent raw envelope role=%s bytes=%r", role, (out or b"")[:2000])

        if returncode not in (0, None):
            snippet = (err or b"").decode("utf-8", "replace")[:300]
            raise SubAgentError(
                role, "non_zero_exit", f"claude -p exited {returncode}: {snippet}"
            )
        try:
            env = json.loads(out or b"{}")
        except (json.JSONDecodeError, ValueError) as exc:
            raise SubAgentError(
                role, "bad_envelope", f"claude -p stdout was not JSON (role={role})"
            ) from exc
        if not isinstance(env, dict):
            raise SubAgentError(
                role, "bad_envelope", f"claude -p envelope was not an object (role={role})"
            )
        if env.get("is_error"):
            _raise_for_envelope(role, env)

        payload = env.get("structured_output")  # parsed object, NOT the `result` str
        if not isinstance(payload, dict):
            raise SubAgentError(
                role,
                "no_structured_output",
                f"envelope had no structured_output object (role={role})",
            )

        stage_cost = capture_cost(role, env)
        emit_cost(stage_cost)  # SC#7 — one structured stderr line per stage
        return RoleResult(role=role, data=payload, cost=stage_cost.model_dump())


async def run_bull_bear(
    backend: DebateBackend,
    *,
    instruction: str,
    bundle_stdin: str,
    prompts: dict[str, str],
    schemas: dict[str, dict],
    timeout_s: float = 180.0,
) -> list[RoleResult]:
    """Run Bull and Bear in PARALLEL, each BLIND to the other (SC#2b).

    Both receive the identical evidence bundle on stdin; neither sees the other's
    output (they are separate calls with no cross-feed). ``prompts`` / ``schemas`` are
    injected by the caller so this module never imports ``roles.py`` (leaf).

    The Judge (SC#2c) is a separate ``backend.run("judge", ..., bundle+bull+bear)``
    call the runner makes AFTER this returns — it is the only role that sees both
    outputs.
    """
    return await asyncio.gather(
        backend.run(
            "bull", instruction, prompts["bull"], schemas["bull"], bundle_stdin,
            timeout_s=timeout_s,
        ),
        backend.run(
            "bear", instruction, prompts["bear"], schemas["bear"], bundle_stdin,
            timeout_s=timeout_s,
        ),
    )
