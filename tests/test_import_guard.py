"""CI test: ingest/ and collectors/ must not import anthropic or openai (COLL-07).

Uses AST parsing to detect import statements. This catches both:
- ``import anthropic``
- ``from anthropic import ...``
- ``from anthropic.types import ...``

The guard scans all .py files recursively under GUARDED_DIRS.
"""

import ast
import textwrap
from pathlib import Path

BANNED_MODULES = {"anthropic", "openai"}
GUARDED_DIRS = ["src/ingest", "src/collectors"]
PROJECT_ROOT = Path(__file__).parent.parent


def scan_for_banned_imports(directory: Path) -> list[str]:
    """Scan all .py files in directory for banned module imports."""
    violations = []
    for py_file in directory.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in BANNED_MODULES:
                        violations.append(f"{py_file}:{node.lineno} imports {alias.name}")
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.split(".")[0] in BANNED_MODULES
            ):
                violations.append(f"{py_file}:{node.lineno} imports from {node.module}")
    return violations


class TestImportGuard:
    def test_no_cloud_llm_imports(self) -> None:
        """No file in src/ingest/ or src/collectors/ imports anthropic or openai."""
        all_violations = []
        for dir_name in GUARDED_DIRS:
            dir_path = PROJECT_ROOT / dir_name
            if dir_path.exists():
                all_violations.extend(scan_for_banned_imports(dir_path))
        assert not all_violations, "Cloud LLM imports found in guarded directories:\n" + "\n".join(
            all_violations
        )

    def test_guard_catches_import(self, tmp_path: Path) -> None:
        """Guard detects 'import anthropic' statement."""
        bad_file = tmp_path / "bad_module.py"
        bad_file.write_text("import anthropic\n", encoding="utf-8")
        violations = scan_for_banned_imports(tmp_path)
        assert len(violations) == 1
        assert "anthropic" in violations[0]

    def test_guard_catches_from_import(self, tmp_path: Path) -> None:
        """Guard detects 'from openai import ...' statement."""
        bad_file = tmp_path / "bad_module.py"
        bad_file.write_text("from openai import ChatCompletion\n", encoding="utf-8")
        violations = scan_for_banned_imports(tmp_path)
        assert len(violations) == 1
        assert "openai" in violations[0]

    def test_guard_passes_clean_file(self, tmp_path: Path) -> None:
        """Guard passes files with only stdlib/allowed imports."""
        clean_file = tmp_path / "clean_module.py"
        clean_file.write_text(
            textwrap.dedent("""\
                import os
                import json
                from pathlib import Path
                from pydantic import BaseModel
            """),
            encoding="utf-8",
        )
        violations = scan_for_banned_imports(tmp_path)
        assert not violations
