"""``list_portfolio`` — read the user portfolio (holdings + watchlist).

Thin passthrough of :meth:`shared.portfolio.Portfolio.load` (the single scope
source: ``notes/private/portfolio.md``). The return is STRUCTURED data (tickers,
quantities, average costs) — NOT narrative — so it gets NO injection wrap (Veto #6
spirit: numbers/identifiers are not embedded/wrapped). Empty holdings or watchlist
is a valid empty :class:`~mcp_v2.models.PortfolioView` (D-01).

A :class:`~shared.portfolio.PortfolioLoadError` (file missing / malformed
frontmatter) is mapped to :class:`~mcp_v2.errors.DataBackendError` — a genuine
fault (the scope source could not be loaded), distinct from a valid empty
portfolio.
"""

from __future__ import annotations

from pathlib import Path

from mcp.types import ToolAnnotations

from shared.portfolio import Portfolio, PortfolioLoadError

from .._mcp import mcp
from ..errors import DataBackendError
from ..models import PortfolioHolding, PortfolioView

__all__ = ["list_portfolio"]

_REPO_ROOT = Path(".")


def list_portfolio() -> PortfolioView:
    """Return the user's holdings + watchlist from ``notes/private/portfolio.md``.

    Returns:
        :class:`PortfolioView` — ``holdings`` (held positions, each with qty +
        avg cost) and ``watchlist`` (monitored tickers). Empty lists are a valid
        empty model (D-01).

    Raises:
        DataBackendError: the portfolio file is missing or its frontmatter is
            malformed (``PortfolioLoadError`` from the loader).
    """
    try:
        portfolio = Portfolio.load(_REPO_ROOT)
    except PortfolioLoadError as exc:
        raise DataBackendError(f"portfolio could not be loaded: {exc}") from exc

    holdings = [
        PortfolioHolding(
            ticker=h.ticker,
            avg_price=h.avg_cost,
            quantity=h.qty,
        )
        for h in portfolio.holdings
    ]
    watchlist = [PortfolioHolding(ticker=t) for t in portfolio.watchlist]
    return PortfolioView(holdings=holdings, watchlist=watchlist)


# Register on the shared mcp via the call form (keeps list_portfolio a plain
# callable for in-process callers; see filing.py for the rationale).
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(list_portfolio)
