"""``get_portfolio_state`` MCP tool — read-only portfolio meta surface (MCP-05, D-21).

Reads ``notes/private/portfolio.md`` (the post-cutover single source of truth
for holdings + watchlist) and returns a ``PortfolioState`` envelope. The
response carries NO market-quote, valuation, or P&L fields — Claude composes
those downstream from market-data tools (D-21 meta-only contract).

Per-row ``corp_code`` is resolved via ``resolve_entity`` so callers can chain
into entity-keyed tools (get_recent_events, get_filing). ``tags`` and
``note`` are reserved for future schema extensions; the current
``Portfolio``/``Holding`` Pydantic models do not surface them, so the tool
emits empty list / None for both fields today (forward-compatible).
"""

from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from db.engine import get_engine
from db.entity import resolve_entity

from ..errors import ErrorCode, StructuredError, to_error_response
from ..logging import log_tool_call
from ..models import PortfolioRow, PortfolioState
from ..repo_root import repo_root
from .search import mcp

__all__ = ["get_portfolio_state"]


def _corp_code_for(engine, ticker: str) -> str | None:
    """Best-effort entity resolution. Returns corp_code or None."""
    try:
        ent = resolve_entity(engine, ticker)
        return ent.corp_code if ent is not None else None
    except Exception:  # noqa: BLE001 — never block portfolio read on resolver
        return None


def get_portfolio_state() -> PortfolioState | dict:
    """Read-only meta surface for the user's portfolio (MCP-05, D-21).

    Reads ``notes/private/portfolio.md`` (gitignored, local-only — the
    post-cutover single source of truth) and returns a ``PortfolioState``
    with separated holdings + watchlist. Each row carries ``ticker``,
    ``corp_code`` (resolved via ``resolve_entity`` — None when unknown),
    ``qty`` + ``avg_cost`` (set on holdings, None on watchlist), plus
    forward-compatible ``tags`` (empty list) and ``note`` (None).

    ### Behavior contract
    - No arguments. The tool reads the fixed path
      ``<repo_root>/notes/private/portfolio.md``; ``repo_root`` is resolved
      via the ``STOCK_REPO_ROOT`` env var (test/CI override) or by walking
      up from cwd for ``pyproject.toml`` + ``vault/``.
    - Holdings rows: ``qty`` and ``avg_cost`` set from the YAML frontmatter;
      ``corp_code`` looked up per ticker.
    - Watchlist rows: ``qty=None``, ``avg_cost=None``; ``corp_code`` looked
      up per ticker.
    - **No market-quote, valuation, or P&L fields are emitted** — the
      response is purely meta. Claude composes those downstream from
      market-data tools (D-21 meta-only contract).
    - ``tags`` / ``note``: today the ``Portfolio`` Pydantic schema does not
      carry per-row tags or notes, so both fields are returned as ``[]`` /
      ``None``. Forward-compatible — Phase 10 may extend the schema.

    ### Response shape
    Returns ``PortfolioState`` with:
    - ``holdings``: list of ``PortfolioRow`` with ``qty`` / ``avg_cost``
      populated.
    - ``watchlist``: list of ``PortfolioRow`` with ``qty=None``,
      ``avg_cost=None``.
    - ``source_path``: always the relative string
      ``"notes/private/portfolio.md"``.
    - ``last_modified``: ``datetime`` of the file's mtime, in
      ``Asia/Seoul``.

    ### Errors
    Returns ``{"error": {"code": ..., "message": ..., "details": {...}}}`` —
    never raises. Codes:
    - ``PATH_NOT_FOUND``: ``notes/private/portfolio.md`` is missing.
    - ``INVALID_FRONTMATTER``: file present but YAML frontmatter is
      malformed or violates the schema (extra keys, bad ticker).
    - ``DB_UNAVAILABLE``: Postgres unreachable while resolving corp_code.
    - ``INTERNAL``: unexpected failure (string truncated to 200 chars).

    ### Performance budget
    p95 latency < 1s. Response < 4k tokens at typical scale (≤ 100 rows).
    Vault is local and gitignored (T-6-05-02 information disclosure
    accepted by design — Claude needs holdings to reason).
    """
    t0 = time.perf_counter()
    args_log: dict = {}
    try:
        root = repo_root()
        portfolio_path = root / "notes" / "private" / "portfolio.md"
        if not portfolio_path.exists():
            raise StructuredError(
                ErrorCode.PATH_NOT_FOUND,
                "portfolio.md not found at notes/private/portfolio.md",
                details={"resolved_path": str(portfolio_path)},
            )

        # Late import: shared.portfolio bundles yaml parsing — keep import
        # local so cold-start cost lands on the first call only.
        from shared.portfolio import Portfolio, PortfolioLoadError

        try:
            portfolio = Portfolio.load(root)
        except PortfolioLoadError as e:
            raise StructuredError(
                ErrorCode.INVALID_FRONTMATTER,
                f"portfolio.md is malformed: {e}",
                details={"resolved_path": str(portfolio_path)},
            ) from e
        except Exception as e:  # pydantic.ValidationError, yaml.YAMLError
            raise StructuredError(
                ErrorCode.INVALID_FRONTMATTER,
                f"portfolio.md schema violation: {str(e)[:160]}",
                details={"resolved_path": str(portfolio_path)},
            ) from e

        engine = get_engine()
        holdings_rows: list[PortfolioRow] = []
        for h in portfolio.holdings:
            holdings_rows.append(
                PortfolioRow(
                    ticker=h.ticker,
                    corp_code=_corp_code_for(engine, h.ticker),
                    qty=float(h.qty),
                    avg_cost=float(h.avg_cost),
                    tags=[],
                    note=None,
                )
            )

        watchlist_rows: list[PortfolioRow] = []
        for ticker in portfolio.watchlist:
            watchlist_rows.append(
                PortfolioRow(
                    ticker=ticker,
                    corp_code=_corp_code_for(engine, ticker),
                    qty=None,
                    avg_cost=None,
                    tags=[],
                    note=None,
                )
            )

        mtime = datetime.fromtimestamp(portfolio_path.stat().st_mtime, tz=ZoneInfo("Asia/Seoul"))
        result = PortfolioState(
            holdings=holdings_rows,
            watchlist=watchlist_rows,
            source_path="notes/private/portfolio.md",
            last_modified=mtime,
        )
        latency = int((time.perf_counter() - t0) * 1000)
        log_tool_call(
            "get_portfolio_state",
            args_log,
            latency,
            len(result.model_dump_json()) // 4,
        )
        return result
    except StructuredError as e:
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(e)
        log_tool_call("get_portfolio_state", args_log, latency, 0, error=err["error"])
        return err
    except Exception as e:  # noqa: BLE001 — D-21 catch-all
        wrapped = StructuredError(ErrorCode.INTERNAL, str(e)[:200])
        latency = int((time.perf_counter() - t0) * 1000)
        err = to_error_response(wrapped)
        log_tool_call("get_portfolio_state", args_log, latency, 0, error=err["error"])
        return err


mcp.tool()(get_portfolio_state)
