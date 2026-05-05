"""GRAPH-01 D-02: INSERT ... ON CONFLICT DO NOTHING — re-running edges.populate()
is a safe no-op."""

import pytest


@pytest.mark.skip(
    reason="Plan 02 Task 2 — populate() called twice yields zero new rows on second call"
)
def test_populate_twice_is_idempotent():
    """First call returns counters['inserted']>0. Second call on same doc_ids
    returns counters['inserted']==0 and counters['skipped_conflict']>=first_inserted."""
    raise NotImplementedError


@pytest.mark.skip(reason="Plan 02 Task 3 — soft-fail: one buggy derivation does not abort batch")
def test_soft_fail_logs_to_failed_per_type():
    """If one _derive_* function raises, populate() catches, fills
    counters['failed_per_type'][edge_type]=str(exc)[:200], and the OTHER
    derivations still run + commit. D-04."""
    raise NotImplementedError
