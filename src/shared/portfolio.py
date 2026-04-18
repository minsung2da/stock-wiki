"""Portfolio model + loader (D-01..D-04).

Single scope source for Phase 4 collectors: every collector calls
`Portfolio.load(vault_root)` and uses `scope_tickers()` (holdings ∪ watchlist)
to decide which tickers to fetch this run.

The vault file `vault/notes/portfolio.md` is the source of truth — a YAML
frontmatter document parsed via python-frontmatter-compatible fence detection.
Validation is strict (extra='forbid') so typos surface as Pydantic errors
rather than silent scope bugs (T-04-01).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

_TICKER_RE = re.compile(r"^[0-9]{6}$")


class PortfolioLoadError(RuntimeError):
    """Raised when vault/notes/portfolio.md cannot be located or parsed."""


class Holding(BaseModel):
    """A single held position: ticker + quantity + average cost (KRW)."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    qty: float = Field(ge=0)
    avg_cost: float = Field(ge=0)

    @field_validator("ticker")
    @classmethod
    def _validate_ticker(cls, v: str) -> str:
        if not _TICKER_RE.match(v):
            raise ValueError(f"ticker must be 6 ASCII digits, got {v!r}")
        return v


class Portfolio(BaseModel):
    """Collector scope source: holdings (owned) + watchlist (monitored)."""

    model_config = ConfigDict(extra="forbid")

    holdings: list[Holding] = Field(default_factory=list)
    watchlist: list[str] = Field(default_factory=list)

    @field_validator("watchlist")
    @classmethod
    def _validate_watchlist(cls, v: list[str]) -> list[str]:
        for t in v:
            if not _TICKER_RE.match(t):
                raise ValueError(f"watchlist ticker must be 6 ASCII digits, got {t!r}")
        return v

    def scope_tickers(self) -> list[str]:
        """Return sorted union of holdings[].ticker and watchlist tickers."""
        return sorted({h.ticker for h in self.holdings} | set(self.watchlist))

    @classmethod
    def load(cls, vault_root: Path) -> Portfolio:
        """Load and validate portfolio.md from `<vault_root>/notes/portfolio.md`.

        Raises:
            PortfolioLoadError: file missing or frontmatter fences absent.
            pydantic.ValidationError: schema violation (bad ticker, extra key, etc.).
        """
        p = Path(vault_root) / "notes" / "portfolio.md"
        if not p.exists():
            raise PortfolioLoadError(f"portfolio.md not found at {p}")
        text = p.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            raise PortfolioLoadError("portfolio.md missing YAML frontmatter opening fence")
        end = text.find("\n---", 4)
        if end < 0:
            raise PortfolioLoadError("portfolio.md frontmatter not terminated")
        data = yaml.safe_load(text[4:end]) or {}
        return cls(**data)
