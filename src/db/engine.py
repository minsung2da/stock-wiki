from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def get_engine() -> Engine:
    """Return a SQLAlchemy 2.0 Engine reading DATABASE_URL from env.

    Raises KeyError if DATABASE_URL is not set (fail-fast, no silent defaults).
    """
    return create_engine(os.environ["DATABASE_URL"], future=True)
