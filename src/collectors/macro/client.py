"""ECOS + FRED client wrappers — fail-fast on missing keys.

T-04-07: Config-error messages name the missing environment variable but
NEVER echo its value (secrets stay out of logs).
"""

from __future__ import annotations

import os


class CollectorConfigError(RuntimeError):
    """Raised when required configuration (API keys, catalog) is missing."""


class MacroEmptyResultError(RuntimeError):
    """Raised per-series when the upstream API returns an empty observation set.

    Treated as a SOFT failure by collect_macro: caught, logged into
    stats['failed'], sibling series continue to run (R-05).
    """


def require_env(name: str) -> str:
    """Return os.environ[name] or raise CollectorConfigError with no value echo."""
    val = os.environ.get(name)
    if not val:
        raise CollectorConfigError(f"{name} missing in environment")
    return val


def ecos_client():
    """Instantiate a PublicDataReader Ecos client. Lazy import so the
    `collectors` dependency group only needs to be installed when running
    macro collection, not during test collection."""
    key = require_env("ECOS_API_KEY")
    from PublicDataReader import Ecos

    return Ecos(service_key=key)


def fred_client():
    """Instantiate a fredapi Fred client. Lazy import (see ecos_client)."""
    key = require_env("FRED_API_KEY")
    from fredapi import Fred

    return Fred(api_key=key)
