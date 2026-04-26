"""UAT helper: zone-integrity check (Phase 5 Success Criterion #2).

For each tracked vault/raw markdown file, compare the `provenance` and
`ingest_state` YAML blocks between two commits (default: PRE = the parent
of the most recent enrichment commit; POST = HEAD on main). A passing
check = these two zones are byte-equal in both commits — the enrichment
agent only wrote `_derived`.

Usage:
    uv run python scripts/uat_zone_integrity.py                  # uses HEAD~1 vs HEAD
    uv run python scripts/uat_zone_integrity.py PRE POST          # explicit refs

Pass criterion: 0 zone violations across all tracked vault/raw docs.
"""

from __future__ import annotations

import subprocess
import sys

import yaml


def _split_frontmatter(text: str) -> dict:
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def main(argv: list[str]) -> int:
    pre = argv[1] if len(argv) > 1 else "HEAD~1"
    post = argv[2] if len(argv) > 2 else "HEAD"

    files = (
        subprocess.check_output(["git", "ls-files", "vault/raw"], text=True).strip().splitlines()
    )

    if not files:
        print("No tracked files under vault/raw/", file=sys.stderr)
        return 2

    violations = 0
    for f in files:
        try:
            pre_text = subprocess.check_output(["git", "show", f"{pre}:{f}"], text=True)
            post_text = subprocess.check_output(["git", "show", f"{post}:{f}"], text=True)
        except subprocess.CalledProcessError:
            continue
        fm_pre = _split_frontmatter(pre_text)
        fm_post = _split_frontmatter(post_text)
        for zone in ("provenance", "ingest_state"):
            if fm_pre.get(zone) != fm_post.get(zone):
                print(f"VIOLATION {f} :: {zone}")
                print(f"  pre  ({pre}):  {fm_pre.get(zone)!r}")
                print(f"  post ({post}): {fm_post.get(zone)!r}")
                violations += 1

    print(f"\n{len(files)} docs · zone violations = {violations}", file=sys.stderr)
    return 0 if violations == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
