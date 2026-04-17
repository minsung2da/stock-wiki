"""Canonical content-hash utility (D-13/D-14).

Computes a stable sha256 hash of a markdown document's body, independent of
its YAML frontmatter and surface whitespace variations. Used for dedup and
content addressing across collectors and ingest. NOT a security primitive —
sha256 collision resistance is assumed for the dedup use case only.

D-13: strip frontmatter before hashing (hash survives frontmatter edits).
D-14: normalize body — CRLF->LF, rstrip each line, single trailing newline.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import frontmatter as fm


def normalize_body(body: str) -> str:
    """Per D-14: CRLF->LF, rstrip each line, single trailing newline."""
    lines = body.replace("\r\n", "\n").split("\n")
    stripped = [ln.rstrip() for ln in lines]
    text = "\n".join(stripped).rstrip("\n") + "\n"
    return text


def compute_content_hash(path: str) -> str:
    """Per D-13: sha256 of frontmatter-stripped, normalized body.

    Returns a 64-char lowercase hex digest.

    Path is resolved via Path.resolve() to eliminate any ../  traversal
    components before the file is opened (D-12 / path-traversal guard).
    """
    resolved = Path(path).resolve()
    post = fm.load(str(resolved))
    return hashlib.sha256(normalize_body(post.content).encode("utf-8")).hexdigest()
