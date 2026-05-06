"""Phase 7.1 SC-3: in-memory graph cache for stock-mcp.

Lazy-loads ``vault/graph/<latest>/graph.json`` into a ``networkx.DiGraph``
on the first ``graph_query`` call. TTL-based invalidation (default 6h,
override via env ``STOCK_MCP_GRAPH_TTL_SECONDS``). On TTL expiry the cache
re-checks the latest graph.json's mtime and reloads if it changed.

Threat-model mitigations (07.1-03 plan):
- T-7.1-03-03 (stale graph held forever): TTL-based invalidation.
- T-7.1-03-04 (huge corpus memory): warning log when ``> 50_000`` nodes.

Compatible with both ``graphify.export.to_json`` output (``links`` key
with ``source``/``target``) and legacy writers using ``edges`` /
``src``/``dst``. The adapter normalizes both shapes before handing to
``networkx.readwrite.json_graph.node_link_graph``.

No LLM dependencies. Reads only the file system + parses JSON.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

from .errors import ErrorCode, StructuredError

__all__ = [
    "GraphCache",
    "get_graph_cache",
    "reset_graph_cache_singleton_for_tests",
]

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 6 * 3600
_NODE_WARN_THRESHOLD = 50_000


class GraphCache:
    """Lazy-loads + TTL-invalidates the latest vault/graph/<DATE>/graph.json.

    Thread-safe via a single re-entrant lock guarding the load path.
    """

    def __init__(
        self,
        vault_graph_dir: Path,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        self._dir = vault_graph_dir
        self._ttl = ttl_seconds if ttl_seconds is not None else _DEFAULT_TTL_SECONDS
        self._G: nx.DiGraph | None = None
        self._loaded_path: Path | None = None
        self._loaded_mtime: float | None = None
        self._loaded_at: float | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def _latest_graph_json(self) -> Path:
        """Return the most recent ``<DATE>/graph.json`` under ``vault/graph/``.

        Raises ``StructuredError(NOT_FOUND)`` when the directory is missing
        or no dated subdir contains ``graph.json``.
        """
        if not self._dir.exists():
            raise StructuredError(
                ErrorCode.NOT_FOUND,
                f"graph dir missing: {self._dir}",
            )
        dated = sorted(
            (
                d
                for d in self._dir.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            ),
            key=lambda p: p.name,
            reverse=True,
        )
        for d in dated:
            gj = d / "graph.json"
            if gj.exists():
                return gj
        raise StructuredError(
            ErrorCode.NOT_FOUND,
            "no graph.json found under vault/graph/",
        )

    # ------------------------------------------------------------------
    # Load / normalize
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(data: dict) -> dict:
        """Return a node-link dict suitable for ``node_link_graph``.

        Accepts both ``links`` and ``edges`` keys and remaps ``src``/``dst``
        to ``source``/``target`` defensively (in case a non-graphify writer
        produced the file).
        """
        raw_links = data.get("links")
        if raw_links is None:
            raw_links = data.get("edges", [])
        normalized_links = []
        for link in raw_links:
            new_link = dict(link)
            if "source" not in new_link and "src" in new_link:
                new_link["source"] = new_link["src"]
            if "target" not in new_link and "dst" in new_link:
                new_link["target"] = new_link["dst"]
            normalized_links.append(new_link)
        return {**data, "links": normalized_links}

    def _load(self, path: Path) -> nx.DiGraph:
        data = json.loads(path.read_text(encoding="utf-8"))
        normalized = self._normalize(data)
        # networkx >= 3.4 defaults edges-key to "edges"; we always normalize
        # to "links" above so pass edges="links" explicitly.
        G = json_graph.node_link_graph(
            normalized,
            directed=True,
            multigraph=False,
            edges="links",
        )
        n_nodes = G.number_of_nodes()
        logger.info(
            "graph_cache: loaded %s (nodes=%d, edges=%d)",
            path,
            n_nodes,
            G.number_of_edges(),
        )
        if n_nodes > _NODE_WARN_THRESHOLD:
            logger.warning(
                "graph_cache: %d nodes exceeds %d — consider tightening "
                "snapshot scope (T-7.1-03-04 DoS mitigation)",
                n_nodes,
                _NODE_WARN_THRESHOLD,
            )
        return G

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def get(self) -> nx.DiGraph:
        """Return the cached ``DiGraph``, reloading if TTL has expired."""
        with self._lock:
            now = time.time()
            ttl_expired = (
                self._loaded_at is None
                or (now - self._loaded_at) >= self._ttl
            )
            if self._G is None or ttl_expired:
                path = self._latest_graph_json()
                mtime = path.stat().st_mtime
                if (
                    self._G is None
                    or self._loaded_path != path
                    or self._loaded_mtime != mtime
                ):
                    self._G = self._load(path)
                    self._loaded_path = path
                    self._loaded_mtime = mtime
                self._loaded_at = now
            assert self._G is not None  # for type-checker
            return self._G


# ----------------------------------------------------------------------
# Singleton helpers
# ----------------------------------------------------------------------
_SINGLETON: GraphCache | None = None


def get_graph_cache(repo_root: Path | None = None) -> GraphCache:
    """Return the process-wide ``GraphCache`` instance, creating it if needed."""
    global _SINGLETON
    if _SINGLETON is None:
        if repo_root is None:
            from .repo_root import repo_root as _rr
            repo_root = _rr()
        ttl = int(
            os.getenv("STOCK_MCP_GRAPH_TTL_SECONDS", str(_DEFAULT_TTL_SECONDS))
        )
        _SINGLETON = GraphCache(
            repo_root / "vault" / "graph",
            ttl_seconds=ttl,
        )
    return _SINGLETON


def reset_graph_cache_singleton_for_tests() -> None:
    """Test-only helper: clear the singleton so a fresh cache is built."""
    global _SINGLETON
    _SINGLETON = None
