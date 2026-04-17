"""Tests for src/shared/content_hash.py — D-13/D-14 determinism."""

from __future__ import annotations

import re
from pathlib import Path

from shared.content_hash import compute_content_hash

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def test_returns_64_char_hex_lowercase(tmp_vault: Path) -> None:
    p = tmp_vault / "a.md"
    p.write_text("Hello body.\n", encoding="utf-8")
    h = compute_content_hash(str(p))
    assert HEX64.match(h), f"hash {h!r} is not 64-char lowercase hex"


def test_deterministic(tmp_vault: Path) -> None:
    p = tmp_vault / "a.md"
    p.write_text("---\nkey: v\n---\nbody line one.\nbody line two.\n", encoding="utf-8")
    assert compute_content_hash(str(p)) == compute_content_hash(str(p))


def test_frontmatter_independent(tmp_vault: Path) -> None:
    body = "Hello body text.\nSecond line.\n"
    (tmp_vault / "a.md").write_text(f"---\nkey: value1\n---\n{body}", encoding="utf-8")
    (tmp_vault / "b.md").write_text(f"---\nkey: value2\nextra: 123\n---\n{body}", encoding="utf-8")
    assert compute_content_hash(str(tmp_vault / "a.md")) == compute_content_hash(
        str(tmp_vault / "b.md")
    )


def test_crlf_normalized(tmp_vault: Path) -> None:
    lf = tmp_vault / "lf.md"
    crlf = tmp_vault / "crlf.md"
    lf.write_bytes(b"line1\nline2\n")
    crlf.write_bytes(b"line1\r\nline2\r\n")
    assert compute_content_hash(str(lf)) == compute_content_hash(str(crlf))


def test_trailing_whitespace_stripped(tmp_vault: Path) -> None:
    clean = tmp_vault / "clean.md"
    dirty = tmp_vault / "dirty.md"
    clean.write_text("line1\nline2\n", encoding="utf-8")
    dirty.write_text("line1   \nline2\t\n", encoding="utf-8")
    assert compute_content_hash(str(clean)) == compute_content_hash(str(dirty))


def test_final_newline_normalized(tmp_vault: Path) -> None:
    zero = tmp_vault / "zero.md"
    one = tmp_vault / "one.md"
    many = tmp_vault / "many.md"
    zero.write_text("body", encoding="utf-8")
    one.write_text("body\n", encoding="utf-8")
    many.write_text("body\n\n\n", encoding="utf-8")
    h_zero = compute_content_hash(str(zero))
    h_one = compute_content_hash(str(one))
    h_many = compute_content_hash(str(many))
    assert h_zero == h_one == h_many


def test_no_frontmatter_file(tmp_vault: Path) -> None:
    p = tmp_vault / "plain.md"
    p.write_text("Just a plain markdown body.\n", encoding="utf-8")
    h = compute_content_hash(str(p))
    assert HEX64.match(h)


def test_different_bodies_differ(tmp_vault: Path) -> None:
    a = tmp_vault / "a.md"
    b = tmp_vault / "b.md"
    a.write_text("content alpha\n", encoding="utf-8")
    b.write_text("content beta\n", encoding="utf-8")
    assert compute_content_hash(str(a)) != compute_content_hash(str(b))
