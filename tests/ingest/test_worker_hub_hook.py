"""Phase 8 Plan 02 Task 3: worker post-cycle hook integration tests.

Verifies that ``ingest_run`` calls ``hub_builder.run`` + ``price_snapshot.run``
at cycle end, and that failures in either module do NOT abort the ingest run
(D-01 best-effort, COLL-08 isolation pattern).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingest import worker as worker_mod


class _SpyEmbedder:
    """Stand-in Embedder so ingest_run skips real model load."""

    def encode(self, texts):
        return [[0.0]] * len(texts)


@pytest.fixture
def fake_engine():
    """Engine sentinel — ingest_run only forwards to hooks; we don't touch DB
    because raw_root is empty (no per-doc work)."""
    class _Conn:
        def execute(self, *a, **kw):
            class _R:
                def all(self_inner):
                    return []

                def first(self_inner):
                    return None

            return _R()

    class _Begin:
        def __enter__(self_inner):
            return _Conn()

        def __exit__(self_inner, *a):
            return False

    class _Engine:
        def begin(self_inner):
            return _Begin()

    return _Engine()


def test_ingest_run_calls_hub_builder(tmp_path: Path, monkeypatch, fake_engine) -> None:
    """Hub builder + price snapshot must each be called exactly once at cycle end."""
    calls: dict[str, int] = {"hub": 0, "price": 0}

    def fake_hub_run(engine, vault_root, repo_root):
        calls["hub"] += 1
        from ingest.hub_builder import HubResult
        return HubResult()

    def fake_price_run(engine, repo_root):
        calls["price"] += 1
        return False

    from ingest import hub_builder, price_snapshot
    monkeypatch.setattr(hub_builder, "run", fake_hub_run)
    monkeypatch.setattr(price_snapshot, "run", fake_price_run)

    # Make raw/ exist but empty so ingest_run loops 0 docs; hooks still fire.
    (tmp_path / "raw").mkdir()
    (tmp_path / "ingested" / "_status").mkdir(parents=True)

    # heartbeat + edges → no-op shims (patch worker_mod's bound names)
    monkeypatch.setattr(worker_mod, "record_source_run", lambda *a, **kw: None)
    monkeypatch.setattr(worker_mod, "edges_populate", lambda *a, **kw: {})

    worker_mod.ingest_run(tmp_path, fake_engine, embedder=_SpyEmbedder())

    assert calls["hub"] == 1
    assert calls["price"] == 1


def test_hub_failure_does_not_kill_ingest(tmp_path: Path, monkeypatch, fake_engine) -> None:
    """hub_builder.run raising must NOT propagate out of ingest_run."""
    def boom(*a, **kw):
        raise RuntimeError("hub build failed")

    from ingest import hub_builder, price_snapshot
    monkeypatch.setattr(hub_builder, "run", boom)
    monkeypatch.setattr(price_snapshot, "run", lambda *a, **kw: False)

    (tmp_path / "raw").mkdir()
    (tmp_path / "ingested" / "_status").mkdir(parents=True)

    monkeypatch.setattr(worker_mod, "record_source_run", lambda *a, **kw: None)
    monkeypatch.setattr(worker_mod, "edges_populate", lambda *a, **kw: {})

    # Should not raise
    stats = worker_mod.ingest_run(tmp_path, fake_engine, embedder=_SpyEmbedder())
    assert isinstance(stats, dict)


def test_price_snapshot_failure_independent(tmp_path: Path, monkeypatch, fake_engine) -> None:
    """price_snapshot raising still allows hub_builder to run."""
    hub_called = {"n": 0}

    def boom(*a, **kw):
        raise RuntimeError("price snap failed")

    def fake_hub(engine, vault_root, repo_root):
        hub_called["n"] += 1
        from ingest.hub_builder import HubResult
        return HubResult()

    from ingest import hub_builder, price_snapshot
    monkeypatch.setattr(price_snapshot, "run", boom)
    monkeypatch.setattr(hub_builder, "run", fake_hub)

    (tmp_path / "raw").mkdir()
    (tmp_path / "ingested" / "_status").mkdir(parents=True)

    monkeypatch.setattr(worker_mod, "record_source_run", lambda *a, **kw: None)
    monkeypatch.setattr(worker_mod, "edges_populate", lambda *a, **kw: {})

    worker_mod.ingest_run(tmp_path, fake_engine, embedder=_SpyEmbedder())

    assert hub_called["n"] == 1
