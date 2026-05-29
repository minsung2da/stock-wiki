"""Phase 1 end-to-end smoke test — vertical slice.

Asserts the v2.0 cutover is intact:

- Migration 0006 is head (verified via the pg_engine fixture's
  ``alembic upgrade head`` in tests/conftest.py).
- The macro collector — simplest vertical slice — INSERTs into
  ``macro_series`` AND writes one row to ``collector_runs``.
- All five collector writer modules are absent from disk (Veto #9
  layer 1).
- ``shared.heartbeat`` is absent (SC-3, Plan 01-08).
- No ``vault/`` directory tree is created during the run (Veto #9 F-3
  enforcement).

Slow-marked because it spins the testcontainer-backed ``pg_clean``
fixture and exercises the full collect path end-to-end.

Phase 1 final closeout artifact — the Success Criteria Coverage
matrix lives in 01-09-SUMMARY.md, not in this test module.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.slow


# ---------- vertical slice: collect_macro DGS10 → DB ---------------------------


def test_phase01_macro_end_to_end(pg_clean, monkeypatch, tmp_path):
    """Minimal end-to-end: one FRED + one ECOS series, mocked fetchers, real DB.

    Asserts:
    - stats['inserted'] == 2; stats['failed'] empty.
    - macro_series has exactly 2 rows (one per series_id).
    - collector_runs has exactly 1 row with source='macro'.
    - No ``vault/`` directory is created under CWD or tmp_path.
    """
    from collectors.macro import client as macro_client
    from collectors.macro import collect_macro, fetcher as macro_fetcher

    # Stub the actual HTTP-bound fetchers — Phase 1 smoke is about DB pathways,
    # not upstream API reachability.
    monkeypatch.setattr(
        macro_fetcher,
        "fetch_ecos_series",
        lambda api, sid, cycle, item_code: [
            {"date": date(2026, 1, 2), "value": 100.0}
        ],
    )
    monkeypatch.setattr(
        macro_fetcher,
        "fetch_fred_series",
        lambda api, sid: [{"date": date(2026, 1, 2), "value": 200.0}],
    )
    # Stub the client constructors — no API keys needed in the smoke.
    monkeypatch.setattr(macro_client, "require_env", lambda _: None)
    monkeypatch.setattr(macro_client, "ecos_client", lambda: object())
    monkeypatch.setattr(macro_client, "fred_client", lambda: object())

    # Minimal catalog so collect_macro has exactly one ECOS + one FRED entry.
    cat = tmp_path / "macro.yaml"
    cat.write_text(
        'ecos:\n'
        '  - {label: "AAA", series_id: "AAA", cycle: "D", item_code: ""}\n'
        'fred:\n'
        '  - {label: "DGS10", series_id: "DGS10"}\n',
        encoding="utf-8",
    )

    # Pin cwd to tmp_path so any accidental "vault/" disk write would land in
    # the test sandbox rather than the developer's working tree.
    monkeypatch.chdir(tmp_path)

    stats = collect_macro(engine=pg_clean, catalog_path=cat)

    assert stats["inserted"] == 2, stats
    assert stats["failed"] == [], stats

    with pg_clean.begin() as conn:
        ms_count = conn.execute(text("SELECT count(*) FROM macro_series")).scalar()
        cr_count = conn.execute(
            text("SELECT count(*) FROM collector_runs WHERE source='macro'")
        ).scalar()
        # Spot-check the seeded values landed
        ecos_value = conn.execute(
            text(
                "SELECT value FROM macro_series "
                "WHERE source='ecos' AND series_id='AAA'"
            )
        ).scalar()
        fred_value = conn.execute(
            text(
                "SELECT value FROM macro_series "
                "WHERE source='fred' AND series_id='DGS10'"
            )
        ).scalar()

    assert ms_count == 2
    assert cr_count == 1
    assert float(ecos_value) == 100.0
    assert float(fred_value) == 200.0

    # Veto #9 fence: no vault/ directory tree was created during the run.
    assert not (tmp_path / "vault").exists()
    assert not (Path.cwd() / "vault").exists()


# ---------- Veto #9 + SC-3 standing assertions ---------------------------------


def test_phase01_writer_files_absent():
    """All five ``src/collectors/<src>/writer.py`` files are gone.

    Defensive duplicate of ``tests/test_no_writer.py::test_writer_files_absent``
    — kept here so the Phase 1 smoke marker (``-m slow``) trips on this
    invariant even when the fast-suite guard is excluded.
    """
    repo_root = Path(__file__).resolve().parents[1]
    for src in ("dart", "krx", "news", "macro", "kind"):
        path = repo_root / "src" / "collectors" / src / "writer.py"
        assert not path.exists(), (
            f"Veto #9 violation: {path} resurrected after Plan 01-09."
        )


def test_phase01_heartbeat_module_absent():
    """``src/shared/heartbeat.py`` is deleted (SC-3 / Plan 01-08).

    Defensive duplicate of ``tests/test_no_heartbeat.py``. Same rationale
    as above — kept here so the Phase 1 smoke run validates SC-3 even
    when fast-suite CI guards are not in the selected marker set.
    """
    repo_root = Path(__file__).resolve().parents[1]
    assert not (repo_root / "src" / "shared" / "heartbeat.py").exists(), (
        "Phase 1 SC-3 violation: shared/heartbeat.py resurrected after Plan 01-08."
    )
