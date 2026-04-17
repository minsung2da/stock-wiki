"""stock CLI subcommand handlers.

Each ``cmd_*`` takes the parsed ``argparse.Namespace`` and returns an int
exit code. Handlers delegate to the domain modules (collectors.dart,
ingest.worker, ingest.rebuild) — CLI logic stays thin so it can be unit-
tested via ``main(argv)`` + monkeypatching at the module boundary.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["cmd_collect_dart", "cmd_ingest_run", "cmd_ingest_rebuild"]


def cmd_collect_dart(args) -> int:  # noqa: ANN001
    """Handle `stock collect dart ...`. Returns exit code.

    Wires ``engine=get_engine()`` so production runs auto-seed
    ``entities``/``entity_aliases`` (Bug C fix, quick-260418-asr). Failure to
    open an engine here bubbles up — the CLI cannot meaningfully continue
    without DB seeding for downstream ``stock ingest run``.
    """
    from collectors.dart import collect_dart
    from db.engine import get_engine

    stats = collect_dart(
        corp_code=args.corp_code,
        since=args.since,
        max_docs=args.max_docs,
        vault_root=Path(args.vault_root),
        engine=get_engine(),
    )
    print(json.dumps(stats, ensure_ascii=False, default=str))
    return 0


def cmd_ingest_run(args) -> int:  # noqa: ANN001
    """Handle `stock ingest run ...`. Returns exit code."""
    from db.engine import get_engine
    from ingest.worker import ingest_run

    stats = ingest_run(
        Path(args.vault_root),
        get_engine(),
        force_reembed=args.force_reembed,
    )
    print(json.dumps(stats, ensure_ascii=False, default=str))
    return 0


def cmd_ingest_rebuild(args) -> int:  # noqa: ANN001
    """Handle `stock ingest rebuild ...` (STORE-05; D-25/28/29). Returns exit code."""
    from db.engine import get_engine
    from ingest.rebuild import rebuild_from_vault

    report = rebuild_from_vault(
        Path(args.vault_root),
        get_engine(),
        force_reembed=args.force_reembed,
        dry_run=args.dry_run,
        assume_yes=args.yes,
    )
    print(json.dumps(report, ensure_ascii=False, default=str))
    if report.get("aborted"):
        return 2
    return 0
