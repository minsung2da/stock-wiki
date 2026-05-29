"""CI fence — Phase 1 SC-1/SC-5/Veto #9. Writer modules must stay deleted.

Three layers of paranoia (RESEARCH.md Q9: "physical deletion + ImportError"):

1. ``test_writer_files_absent`` — direct disk scan.
2. ``test_writer_modules_not_importable`` — even if a stub ``writer/__init__.py``
   package is dropped under a collector, the module name must not resolve.
3. ``test_no_collector_imports_writer`` — AST scan of each collector's
   ``__init__.py`` so a future regression that just re-adds the import line
   trips here (even if no writer.py file exists at that moment).

Plan 01-09 enforces F-3 (verification doc): the suite-time fence should
catch ANY ``.md`` write under ``vault/`` while the test session runs, not
just the specific known paths the writers used. That broader Markdown-write
scan is implemented as ``test_no_vault_markdown_written_during_session`` —
a directory walk at session end.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COLLECTORS: tuple[str, ...] = ("dart", "krx", "news", "macro", "kind")


def test_writer_files_absent() -> None:
    """Each ``src/collectors/<src>/writer.py`` is gone from disk."""
    offenders = [
        f"src/collectors/{src}/writer.py"
        for src in _COLLECTORS
        if (_REPO_ROOT / "src" / "collectors" / src / "writer.py").exists()
    ]
    assert not offenders, (
        f"vault writer modules resurrected: {offenders}. "
        "Phase 1 v2.0 Veto #9: Markdown vault is dead; collectors INSERT to Postgres."
    )


def test_writer_modules_not_importable() -> None:
    """``collectors.<src>.writer`` does not resolve in importlib.

    Catches the case where someone re-creates the package as a stub
    (``writer/__init__.py``) instead of a flat ``.py`` file — the disk
    scan above would miss that, but ``find_spec`` would not.
    """
    offenders: list[str] = []
    for src in _COLLECTORS:
        mod = f"collectors.{src}.writer"
        try:
            spec = importlib.util.find_spec(mod)
        except ModuleNotFoundError:
            # Parent package can't be found, which is itself a hard absent;
            # not a regression vector for writer-revival.
            spec = None
        if spec is not None:
            offenders.append(mod)
    assert not offenders, (
        f"writer modules importable: {offenders}. "
        "Even if the .py file is absent, a stub or __init__-shadow could leak."
    )


def test_no_collector_imports_writer() -> None:
    """``collectors/<src>/__init__.py`` does not import ``writer``.

    Static AST scan — catches a regression where someone re-adds
    ``from .writer import write_*`` even before the writer file itself
    is recreated.
    """
    offenders: list[str] = []
    for src in _COLLECTORS:
        init_path = _REPO_ROOT / "src" / "collectors" / src / "__init__.py"
        if not init_path.exists():  # pragma: no cover — collector itself missing
            continue
        tree = ast.parse(init_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                # Direct `from collectors.<src>.writer import X`
                if module.endswith(".writer") or module == "writer":
                    offenders.append(str(init_path))
                    break
                # `from collectors.<src> import writer`
                if module == f"collectors.{src}" and any(
                    a.name == "writer" for a in node.names
                ):
                    offenders.append(str(init_path))
                    break
            elif isinstance(node, ast.Import):
                # `import collectors.<src>.writer` (rare but possible)
                for alias in node.names:
                    if alias.name == f"collectors.{src}.writer":
                        offenders.append(str(init_path))
                        break
    assert not offenders, (
        f"collector __init__.py still references writer: {offenders}"
    )


def test_no_vault_markdown_written_during_session(tmp_path_factory) -> None:
    """F-3 enforcement: nothing in the test session should be writing
    ``.md`` files under a ``vault/`` directory tree anywhere on disk.

    Walks the repo root and any tmp_path roots used by the session and
    asserts no ``.md`` file lives under a path component named ``vault``.
    The walk excludes the planning notes vault (``.planning/``) and the
    user thesis vault (``notes/private/``) which are documented Markdown
    locations independent of the deleted collector writer modules.

    Phase 1 verification doc F-3: the CI guard should catch ANY .md write
    under vault/ during a collect run, not just specific known paths.
    """
    suspicious: list[str] = []

    # Scan the repo's own working tree
    for md in _REPO_ROOT.rglob("*.md"):
        parts = md.parts
        if "vault" in parts:
            # Skip the user notes vault (allowed by CLAUDE.md — gitignored)
            if "notes" in parts and "private" in parts:
                continue
            # Skip the planning subdirectory (project artifacts, not collector output)
            if ".planning" in parts:
                continue
            # Skip our own test-fixture vault scaffolds, if any
            if "tests" in parts and "fixtures" in parts:
                continue
            suspicious.append(str(md.relative_to(_REPO_ROOT)))

    # Also scan pytest's per-session tmp root — covers tests that monkeypatch.chdir
    # and might write under <tmp>/vault/raw/<src>/*.md
    try:
        session_root = tmp_path_factory.getbasetemp()
    except Exception:  # pragma: no cover — defensive against fixture lifecycle changes
        session_root = None
    if session_root is not None and Path(session_root).exists():
        for md in Path(session_root).rglob("*.md"):
            if "vault" in md.parts:
                suspicious.append(str(md))

    assert not suspicious, (
        f"Veto #9 violation — Markdown files found under a 'vault/' path: "
        f"{suspicious[:10]}{'...' if len(suspicious) > 10 else ''}. "
        "Collectors must INSERT to Postgres; no vault disk writes are permitted."
    )
