"""Quick task 260426-k8h: collectors preserve carried `_derived` block.

Regression coverage for the 2026-04-26 macro re-collect bug where
`stock collect macro` wiped 4 prior Routine-enriched `_derived` blocks.

Per CONTEXT.md D-01 ("All collectors") this exercises macro as the proven
failure case end-to-end and proves all 5 writers got the patch via grep.
"""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_type
from pathlib import Path

from shared.frontmatter import (
    DerivedBlock,
    FrontMatter,
    IngestStateBlock,
    Observation,
    ProvenanceBlock,
    read_frontmatter,
    write_frontmatter,
)

# ---------------------------------------------------------------------------
# Grep guard — proves all 5 writers got the patch.
# ---------------------------------------------------------------------------


def test_all_writers_call_read_existing_derived() -> None:
    """Every collector writer must import and call read_existing_derived."""
    repo_root = Path(__file__).resolve().parent.parent
    for collector in ("macro", "krx", "news", "dart", "kind"):
        src = (repo_root / "src" / "collectors" / collector / "writer.py").read_text()
        assert "read_existing_derived" in src, (
            f"{collector}/writer.py missing read_existing_derived call"
        )


# ---------------------------------------------------------------------------
# Macro carry-forward integration tests (proven failure case).
# ---------------------------------------------------------------------------


def _seed_macro_doc(path: Path, *, content_hash: str, derived: DerivedBlock | None) -> None:
    """Pre-write a macro doc with a populated _derived to simulate a prior Routine pass."""
    path.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {}
    if derived is not None:
        kwargs["derived"] = derived
    fm = FrontMatter(
        provenance=ProvenanceBlock(
            source="ecos",
            source_id="722Y001",
            content_hash=content_hash,
            observations=[Observation(date=date_type(2026, 4, 1), value=1.0)],
        ),
        **kwargs,
    )
    write_frontmatter(
        str(path), fm, "## prior\n\n| date | value |\n|---|---|\n| 2026-04-01 | 1.0 |\n"
    )


def test_macro_writer_carries_prior_derived(tmp_vault: Path) -> None:
    """write_macro_doc preserves prior _derived when body changes."""
    from collectors.macro.writer import vault_path_for_macro, write_macro_doc

    path = vault_path_for_macro(tmp_vault, "ecos", "722Y001")
    populated = DerivedBlock(tickers=["MACRO_X"], summary="prior")
    _seed_macro_doc(path, content_hash="OLD", derived=populated)

    new_obs = [{"date": "2026-04-26", "value": 99.9}]
    written, new_hash, rewrote, _revisions = write_macro_doc(
        vault_root=tmp_vault,
        source="ecos",
        series_id="722Y001",
        label="722Y001",
        observations=new_obs,
        source_url="https://ecos.bok.or.kr/api/",
    )
    assert rewrote is True
    assert new_hash != "OLD"

    fm, _body = read_frontmatter(str(written))
    assert fm.derived.tickers == ["MACRO_X"]
    assert fm.derived.summary == "prior"
    assert fm.provenance.content_hash == new_hash


def test_macro_writer_first_write_default_derived(tmp_vault: Path) -> None:
    """No prior file → fresh empty DerivedBlock written (no carry)."""
    from collectors.macro.writer import write_macro_doc

    written, _hash, rewrote, _ = write_macro_doc(
        vault_root=tmp_vault,
        source="ecos",
        series_id="722Y001",
        label="722Y001",
        observations=[{"date": "2026-04-26", "value": 99.9}],
        source_url="https://ecos.bok.or.kr/api/",
    )
    assert rewrote is True
    fm, _body = read_frontmatter(str(written))
    assert fm.derived == DerivedBlock()


def test_macro_writer_malformed_prior_is_non_fatal(tmp_vault: Path) -> None:
    """Corrupt prior file → no exception; default empty DerivedBlock written."""
    from collectors.macro.writer import vault_path_for_macro, write_macro_doc

    path = vault_path_for_macro(tmp_vault, "ecos", "722Y001")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\nnot: [valid yaml\n---\nbody")

    written, _hash, rewrote, _ = write_macro_doc(
        vault_root=tmp_vault,
        source="ecos",
        series_id="722Y001",
        label="722Y001",
        observations=[{"date": "2026-04-26", "value": 99.9}],
        source_url="https://ecos.bok.or.kr/api/",
    )
    assert rewrote is True
    fm, _body = read_frontmatter(str(written))
    assert fm.derived == DerivedBlock()


# ---------------------------------------------------------------------------
# Quick task 260426-mic: ingest_state.injection_flags carry-forward.
# ---------------------------------------------------------------------------


def test_all_writers_call_read_existing_injection_flags() -> None:
    """Every collector writer must import and call read_existing_injection_flags."""
    repo_root = Path(__file__).resolve().parent.parent
    for collector in ("macro", "krx", "news", "dart", "kind"):
        src = (repo_root / "src" / "collectors" / collector / "writer.py").read_text()
        assert "read_existing_injection_flags" in src, (
            f"{collector}/writer.py missing read_existing_injection_flags call"
        )


def _seed_macro_doc_with_ingest_state(
    path: Path, *, content_hash: str, ingest_state: IngestStateBlock
) -> None:
    """Pre-write a macro doc with a custom IngestStateBlock to simulate a prior ingest pass."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = FrontMatter(
        provenance=ProvenanceBlock(
            source="ecos",
            source_id="722Y001",
            content_hash=content_hash,
            observations=[Observation(date=date_type(2026, 4, 1), value=1.0)],
        ),
        ingest_state=ingest_state,
    )
    write_frontmatter(
        str(path), fm, "## prior\n\n| date | value |\n|---|---|\n| 2026-04-01 | 1.0 |\n"
    )


def test_macro_writer_carries_prior_injection_flags(tmp_vault: Path) -> None:
    """write_macro_doc preserves prior injection_flags when body changes."""
    from collectors.macro.writer import vault_path_for_macro, write_macro_doc

    path = vault_path_for_macro(tmp_vault, "ecos", "722Y001")
    _seed_macro_doc_with_ingest_state(
        path,
        content_hash="OLD",
        ingest_state=IngestStateBlock(injection_flags=["HIDDEN_INSTRUCTION"]),
    )

    written, new_hash, rewrote, _revisions = write_macro_doc(
        vault_root=tmp_vault,
        source="ecos",
        series_id="722Y001",
        label="722Y001",
        observations=[{"date": "2026-04-26", "value": 99.9}],
        source_url="https://ecos.bok.or.kr/api/",
    )
    assert rewrote is True
    assert new_hash != "OLD"

    fm, _body = read_frontmatter(str(written))
    assert fm.ingest_state.injection_flags == ["HIDDEN_INSTRUCTION"]
    assert fm.provenance.content_hash == new_hash


def test_macro_writer_first_write_default_injection_flags(tmp_vault: Path) -> None:
    """No prior file → fresh empty injection_flags list (no carry)."""
    from collectors.macro.writer import write_macro_doc

    written, _hash, rewrote, _ = write_macro_doc(
        vault_root=tmp_vault,
        source="ecos",
        series_id="722Y001",
        label="722Y001",
        observations=[{"date": "2026-04-26", "value": 99.9}],
        source_url="https://ecos.bok.or.kr/api/",
    )
    assert rewrote is True
    fm, _body = read_frontmatter(str(written))
    assert fm.ingest_state.injection_flags == []


def test_macro_writer_malformed_prior_injection_flags_non_fatal(tmp_vault: Path) -> None:
    """Corrupt prior file → no exception; default empty IngestStateBlock written."""
    from collectors.macro.writer import vault_path_for_macro, write_macro_doc

    path = vault_path_for_macro(tmp_vault, "ecos", "722Y001")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\nnot: [valid yaml\n---\nbody")

    written, _hash, rewrote, _ = write_macro_doc(
        vault_root=tmp_vault,
        source="ecos",
        series_id="722Y001",
        label="722Y001",
        observations=[{"date": "2026-04-26", "value": 99.9}],
        source_url="https://ecos.bok.or.kr/api/",
    )
    assert rewrote is True
    fm, _body = read_frontmatter(str(written))
    assert fm.ingest_state == IngestStateBlock()


def test_macro_writer_scope_lock_other_ingest_state_fields_reset(tmp_vault: Path) -> None:
    """Scope lock: ONLY injection_flags is preserved; other ingest_state fields reset.

    Locks the contract that processed/processed_at/embedding_model/ingest_model/
    ingest_version are pipeline-state markers owned by the ingest worker —
    they MUST reset on collector rewrite so re-processing is correctly triggered.
    """
    from collectors.macro.writer import vault_path_for_macro, write_macro_doc

    path = vault_path_for_macro(tmp_vault, "ecos", "722Y001")
    _seed_macro_doc_with_ingest_state(
        path,
        content_hash="OLD",
        ingest_state=IngestStateBlock(
            processed=True,
            processed_at=datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC),
            embedding_model="bge-m3",
            ingest_model="claude-haiku-4-5",
            ingest_version=1,
            injection_flags=["X"],
        ),
    )

    written, _new_hash, rewrote, _ = write_macro_doc(
        vault_root=tmp_vault,
        source="ecos",
        series_id="722Y001",
        label="722Y001",
        observations=[{"date": "2026-04-26", "value": 99.9}],
        source_url="https://ecos.bok.or.kr/api/",
    )
    assert rewrote is True
    fm, _body = read_frontmatter(str(written))

    # The sole survivor:
    assert fm.ingest_state.injection_flags == ["X"]
    # Everything else MUST reset to defaults:
    assert fm.ingest_state.processed is False
    assert fm.ingest_state.processed_at is None
    assert fm.ingest_state.embedding_model is None
    assert fm.ingest_state.ingest_model is None
    assert fm.ingest_state.ingest_version is None
