"""Phase 8 Plan 03 — Task 1: Dataview plugin bootstrap verification.

Validates D-16 (community-plugins.json registration) + D-17 (recommended
settings) + D-18 (DataviewJS disabled).
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMUNITY_PLUGINS_PATH = REPO_ROOT / ".obsidian" / "community-plugins.json"
DATAVIEW_DATA_PATH = REPO_ROOT / ".obsidian" / "plugins" / "dataview" / "data.json"


def test_community_plugins_includes_dataview() -> None:
    """D-16: Obsidian must auto-prompt to install Dataview on first open."""
    assert COMMUNITY_PLUGINS_PATH.exists(), (
        f"Missing {COMMUNITY_PLUGINS_PATH}; required by Phase 8 D-16"
    )
    payload = json.loads(COMMUNITY_PLUGINS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, list), (
        "community-plugins.json must be a JSON array of plugin ids"
    )
    assert "dataview" in payload, (
        f"`dataview` not registered in community-plugins.json: {payload}"
    )


def test_dataview_data_json_recommended_settings() -> None:
    """D-17: Exact recommended Dataview settings."""
    assert DATAVIEW_DATA_PATH.exists(), (
        f"Missing {DATAVIEW_DATA_PATH}; required by Phase 8 D-17"
    )
    settings = json.loads(DATAVIEW_DATA_PATH.read_text(encoding="utf-8"))

    expected = {
        "enableDataviewJs": False,
        "enableInlineDataview": True,
        "enableInlineDataviewJs": False,
        "renderNullAs": "—",
        "warnOnEmptyResult": True,
        "refreshEnabled": True,
        "refreshInterval": 2500,
    }
    for key, value in expected.items():
        assert key in settings, f"D-17 key missing: {key}"
        assert settings[key] == value, (
            f"D-17 mismatch for {key}: expected {value!r}, got {settings[key]!r}"
        )


def test_dataviewjs_disabled() -> None:
    """D-18 + T-08-03-01: DataviewJS must be explicitly disabled."""
    settings = json.loads(DATAVIEW_DATA_PATH.read_text(encoding="utf-8"))
    assert settings.get("enableDataviewJs") is False, (
        "T-08-03-01: enableDataviewJs must be explicitly false"
    )
    assert settings.get("enableInlineDataviewJs") is False, (
        "T-08-03-01: enableInlineDataviewJs must be explicitly false"
    )
