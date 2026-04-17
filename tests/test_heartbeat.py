"""Tests for ProvenanceBlock.trust_level (D-19) and heartbeat atomic write (COLL-09).

Covers:
- trust_level default 'trusted' + YAML round-trip + validation rejection of unknown values
- record_source_run creates heartbeat file with sources dict (D-15, Pattern 8)
- Preserves other sources across updates
- Records last_failure when any filings failed; preserves prior last_success
- Atomic write via tempfile+os.replace; no .tmp leftovers on crash (Pitfall 6)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from pydantic import ValidationError

from ingest.heartbeat import record_source_run
from shared.frontmatter import (
    FrontMatter,
    ProvenanceBlock,
    read_frontmatter,
    write_frontmatter,
)


def _load_heartbeat_sources(path: Path) -> dict[str, Any]:
    """Heartbeat file has frontmatter with a top-level 'sources' dict.

    Load via yaml.safe_load since 'sources' is outside FrontMatter's Pydantic schema.
    """
    text = path.read_text(encoding="utf-8")
    # python-frontmatter style: metadata between --- delimiters.
    if not text.startswith("---"):
        raise AssertionError(f"heartbeat missing frontmatter delimiters: {text!r}")
    end = text.find("\n---", 3)
    assert end != -1, "heartbeat missing closing ---"
    raw_yaml = text[3:end]
    return yaml.safe_load(raw_yaml) or {}


class TestProvenanceTrustLevel:
    def test_provenance_trust_level_default_trusted(self) -> None:
        """ProvenanceBlock(source='dart') has trust_level='trusted' by default (D-19)."""
        p = ProvenanceBlock(source="dart")
        assert p.trust_level == "trusted"

    def test_provenance_trust_level_roundtrips_yaml(self, tmp_path: Path) -> None:
        """trust_level='semi_trusted' round-trips through write/read_frontmatter."""
        path = str(tmp_path / "rt.md")
        fm = FrontMatter(provenance=ProvenanceBlock(source="news", trust_level="semi_trusted"))
        write_frontmatter(path, fm, "body")
        raw = Path(path).read_text(encoding="utf-8")
        assert "trust_level: semi_trusted" in raw
        fm2, _ = read_frontmatter(path)
        assert fm2.provenance.trust_level == "semi_trusted"

    def test_provenance_trust_level_rejects_unknown(self) -> None:
        """Unknown trust_level raises ValidationError."""
        with pytest.raises(ValidationError):
            ProvenanceBlock(source="dart", trust_level="bogus")  # type: ignore[arg-type]


class TestHeartbeat:
    def test_heartbeat_creates_file_on_first_run(self, tmp_path: Path) -> None:
        """record_source_run creates heartbeat.md with sources.dart populated."""
        hb = tmp_path / "vault/ingested/_status/heartbeat.md"
        record_source_run(
            "dart",
            {"total": 3, "succeeded": 3, "skipped": 0, "failed": []},
            heartbeat_path=hb,
        )
        assert hb.exists()
        meta = _load_heartbeat_sources(hb)
        assert "sources" in meta
        assert "dart" in meta["sources"]
        dart = meta["sources"]["dart"]
        assert dart["last_run"]
        assert dart["last_success"]
        assert dart["docs_processed"] == 3

    def test_heartbeat_preserves_other_sources_on_update(self, tmp_path: Path) -> None:
        """Recording krx after dart keeps both source blocks with distinct timestamps."""
        hb = tmp_path / "hb.md"
        record_source_run(
            "dart",
            {"total": 1, "succeeded": 1, "skipped": 0, "failed": []},
            heartbeat_path=hb,
        )
        meta1 = _load_heartbeat_sources(hb)
        dart_run_1 = meta1["sources"]["dart"]["last_run"]

        record_source_run(
            "krx",
            {"total": 2, "succeeded": 2, "skipped": 0, "failed": []},
            heartbeat_path=hb,
        )
        meta2 = _load_heartbeat_sources(hb)
        assert "dart" in meta2["sources"]
        assert "krx" in meta2["sources"]
        # dart block preserved verbatim (last_run unchanged).
        assert meta2["sources"]["dart"]["last_run"] == dart_run_1

    def test_heartbeat_records_failure_on_failed_docs(self, tmp_path: Path) -> None:
        """Failed run records last_failure; prior last_success preserved."""
        hb = tmp_path / "hb.md"
        # First: a fully successful run.
        record_source_run(
            "dart",
            {"total": 1, "succeeded": 1, "skipped": 0, "failed": []},
            heartbeat_path=hb,
        )
        success_ts = _load_heartbeat_sources(hb)["sources"]["dart"]["last_success"]

        # Second: partial failure.
        record_source_run(
            "dart",
            {"total": 2, "succeeded": 1, "skipped": 0, "failed": [{"doc": "x", "error": "boom"}]},
            heartbeat_path=hb,
        )
        meta = _load_heartbeat_sources(hb)
        dart = meta["sources"]["dart"]
        assert dart["last_failure"]
        # last_success from previous run preserved.
        assert dart["last_success"] == success_ts

    def test_heartbeat_atomic_write_survives_crash(self, tmp_path: Path) -> None:
        """If os.replace fails mid-write, heartbeat is unchanged and no .tmp left behind."""
        hb = tmp_path / "hb.md"
        status_dir = hb.parent
        # Pre-create the status dir so we can check for leftover .tmp files.
        status_dir.mkdir(parents=True, exist_ok=True)

        def boom(src: str, dst: str) -> None:
            raise OSError("simulated crash")

        with (
            patch("ingest.heartbeat.os.replace", side_effect=boom),
            pytest.raises(OSError),
        ):
            record_source_run(
                "dart",
                {"total": 1, "succeeded": 1, "skipped": 0, "failed": []},
                heartbeat_path=hb,
            )

        assert not hb.exists(), "heartbeat should not have been created on crash"
        tmp_leftovers = list(status_dir.glob("*.tmp"))
        assert tmp_leftovers == [], f"leftover .tmp files: {tmp_leftovers}"

        # Now a good write should still work normally after crash-recovery.
        record_source_run(
            "dart",
            {"total": 1, "succeeded": 1, "skipped": 0, "failed": []},
            heartbeat_path=hb,
        )
        assert hb.exists()

    def test_heartbeat_atomic_write_preserves_existing_on_crash(self, tmp_path: Path) -> None:
        """If file existed before crash, it remains unchanged after a failing write."""
        hb = tmp_path / "hb.md"
        # Write a good initial heartbeat.
        record_source_run(
            "dart",
            {"total": 1, "succeeded": 1, "skipped": 0, "failed": []},
            heartbeat_path=hb,
        )
        original = hb.read_text(encoding="utf-8")

        def boom(src: str, dst: str) -> None:
            raise OSError("simulated crash")

        with (
            patch("ingest.heartbeat.os.replace", side_effect=boom),
            pytest.raises(OSError),
        ):
            record_source_run(
                "krx",
                {"total": 1, "succeeded": 1, "skipped": 0, "failed": []},
                heartbeat_path=hb,
            )
        assert hb.read_text(encoding="utf-8") == original
        assert list(hb.parent.glob("*.tmp")) == []

    def test_heartbeat_docs_processed_matches_succeeded(self, tmp_path: Path) -> None:
        """docs_processed tracks succeeded count specifically (not total)."""
        hb = tmp_path / "hb.md"
        record_source_run(
            "dart",
            {"total": 5, "succeeded": 3, "skipped": 1, "failed": [{"doc": "a", "error": "e"}]},
            heartbeat_path=hb,
        )
        dart = _load_heartbeat_sources(hb)["sources"]["dart"]
        assert dart["docs_processed"] == 3
