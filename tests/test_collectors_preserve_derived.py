"""Quick task 260426-k8h: collectors preserve carried `_derived` block.

Regression coverage for the 2026-04-26 macro re-collect bug where
`stock collect macro` wiped 4 prior Routine-enriched `_derived` blocks.

Per CONTEXT.md D-01 ("All collectors") this exercises macro as the proven
failure case end-to-end and proves all 5 writers got the patch via grep.
"""

from __future__ import annotations

from datetime import date as date_type
from pathlib import Path

from shared.frontmatter import (
    DerivedBlock,
    FrontMatter,
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
