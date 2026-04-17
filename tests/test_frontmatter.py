"""Tests for Pydantic frontmatter 3-zone schema (FOUND-06).

Validates:
- YAML round-trip without data loss
- Zone isolation (updating one zone doesn't affect others)
- Alias handling for _derived key
- Default values
- File read/write cycle
"""

from pathlib import Path

import frontmatter as fm
import pytest
from pydantic import ValidationError

from shared.frontmatter import (
    DerivedBlock,
    FrontMatter,
    IngestStateBlock,
    ProvenanceBlock,
    read_frontmatter,
    write_frontmatter,
)


class TestFrontMatterRoundTrip:
    def test_frontmatter_round_trip(self, sample_yaml: str) -> None:
        """FrontMatter model round-trips through YAML without data loss."""
        post = fm.loads(sample_yaml)
        model = FrontMatter.model_validate(dict(post.metadata))

        assert model.provenance.source == "dart"
        assert model.provenance.corp_code == "00126380"
        assert model.provenance.ticker == "005930"
        assert model.provenance.content_hash == "sha256:abc123def456"
        assert model.ingest_state.processed is False

        dumped = model.model_dump(by_alias=True, exclude_none=True)
        post2 = fm.Post("Test body.")
        post2.metadata = dumped
        yaml_str = fm.dumps(post2)

        post3 = fm.loads(yaml_str)
        model2 = FrontMatter.model_validate(dict(post3.metadata))

        assert model2.provenance.source == model.provenance.source
        assert model2.provenance.corp_code == model.provenance.corp_code
        assert model2.provenance.ticker == model.provenance.ticker
        assert model2.provenance.content_hash == model.provenance.content_hash
        assert model2.ingest_state.processed == model.ingest_state.processed

    def test_zone_isolation(self, sample_yaml: str) -> None:
        """Each zone can be updated independently without affecting others."""
        post = fm.loads(sample_yaml)
        model = FrontMatter.model_validate(dict(post.metadata))

        updated = model.model_copy(
            update={"ingest_state": IngestStateBlock(processed=True, embedding_model="bge-m3")}
        )

        assert updated.provenance.source == "dart"
        assert updated.provenance.corp_code == "00126380"
        assert updated.ingest_state.processed is True
        assert updated.ingest_state.embedding_model == "bge-m3"
        assert updated.derived.tickers == []

    def test_derived_update_isolation(self, sample_yaml: str) -> None:
        """Updating _derived zone doesn't affect provenance or ingest_state."""
        post = fm.loads(sample_yaml)
        model = FrontMatter.model_validate(dict(post.metadata))

        updated = model.model_copy(
            update={
                "derived": DerivedBlock(
                    tickers=["005930"],
                    event_type="earnings",
                    summary="Q4 earnings report",
                )
            }
        )

        assert updated.provenance.source == "dart"
        assert updated.ingest_state.processed is False
        assert updated.derived.tickers == ["005930"]
        assert updated.derived.event_type == "earnings"


class TestProvenanceValidation:
    def test_provenance_block_required_fields(self) -> None:
        """FrontMatter requires at minimum provenance.source."""
        with pytest.raises(ValidationError):
            FrontMatter.model_validate({"provenance": {}})

    def test_provenance_with_source_only(self) -> None:
        """Minimal valid FrontMatter has only provenance.source."""
        model = FrontMatter.model_validate({"provenance": {"source": "note"}})
        assert model.provenance.source == "note"
        assert model.provenance.lang == "ko"


class TestDerivedAlias:
    def test_derived_alias_from_yaml(self, sample_yaml: str) -> None:
        """_derived key in YAML maps to DerivedBlock via alias."""
        post = fm.loads(sample_yaml)
        metadata = dict(post.metadata)
        assert "_derived" in metadata
        model = FrontMatter.model_validate(metadata)
        assert isinstance(model.derived, DerivedBlock)

    def test_derived_alias_to_yaml(self) -> None:
        """model_dump(by_alias=True) emits '_derived' key."""
        model = FrontMatter(
            provenance=ProvenanceBlock(source="note"),
            derived=DerivedBlock(tickers=["005930"]),
        )
        dumped = model.model_dump(by_alias=True, exclude_none=True)
        assert "_derived" in dumped
        assert "derived" not in dumped
        assert dumped["_derived"]["tickers"] == ["005930"]


class TestDefaultValues:
    def test_default_values(self) -> None:
        """FrontMatter with only provenance has correct defaults."""
        model = FrontMatter(provenance=ProvenanceBlock(source="dart"))
        assert model.ingest_state.processed is False
        assert model.ingest_state.processed_at is None
        assert model.derived.tickers == []
        assert model.derived.catalysts == []
        assert model.derived.numeric_facts == []
        assert model.derived.sentiment is None
        assert model.derived.summary is None


class TestFileReadWrite:
    def test_write_and_read_file(self, tmp_vault: Path) -> None:
        """write_frontmatter() creates a file, read_frontmatter() reads it back."""
        file_path = str(tmp_vault / "test_write.md")
        body = "This is the document body."

        model = FrontMatter(
            provenance=ProvenanceBlock(
                source="dart",
                corp_code="00126380",
                ticker="005930",
                content_hash="sha256:test123",
            ),
            ingest_state=IngestStateBlock(processed=True, embedding_model="bge-m3"),
            derived=DerivedBlock(tickers=["005930"], summary="Test summary"),
        )

        write_frontmatter(file_path, model, body)
        assert Path(file_path).exists()

        model2, body2 = read_frontmatter(file_path)
        assert body2.strip() == body
        assert model2.provenance.source == "dart"
        assert model2.provenance.corp_code == "00126380"
        assert model2.ingest_state.processed is True
        assert model2.ingest_state.embedding_model == "bge-m3"
        assert model2.derived.tickers == ["005930"]
        assert model2.derived.summary == "Test summary"

    def test_read_existing_file(self, sample_md_file: Path) -> None:
        """read_frontmatter() correctly parses an existing markdown file."""
        model, body = read_frontmatter(str(sample_md_file))
        assert model.provenance.source == "dart"
        assert model.provenance.source_id == "20260416000523"
        assert "Samsung Electronics" in body
