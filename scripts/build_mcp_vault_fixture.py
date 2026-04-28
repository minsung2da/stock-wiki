"""Build the deterministic MCP-vault test fixture (Phase 6 Plan 06-03 Task 2).

Generates ``tests/fixtures/mcp-vault/`` with ≥10 tickers and ≥100 documents
spread across DART (≥30), news (≥40), KIND (≥20), and user notes (≥10),
plus a portfolio.md and an ingest heartbeat. The generator is byte-deterministic
(``random.Random(seed=42)``) so re-running ``--clean`` reproduces the same tree.

Usage:
    uv run python scripts/build_mcp_vault_fixture.py --out tests/fixtures/mcp-vault --clean

Frontmatter shape mirrors ``src.shared.frontmatter.FrontMatter`` (provenance
+ ingest_state + _derived). The body is a small Korean snippet sized
200-2000 chars so ingest chunking has realistic input.
"""

from __future__ import annotations

import argparse
import hashlib
import random
import shutil
import sys
from pathlib import Path

# 10 distinct tickers (3 holdings + 7 watchlist) with synthetic corp_codes.
TICKERS: list[tuple[str, str, str]] = [
    # (ticker, corp_code, korean_name)
    ("005930", "00126380", "삼성전자"),
    ("000660", "00164779", "SK하이닉스"),
    ("035720", "00256598", "카카오"),
    ("035420", "00266961", "NAVER"),
    ("051910", "00356361", "LG화학"),
    ("207940", "00877059", "삼성바이오로직스"),
    ("068270", "00421196", "셀트리온"),
    ("323410", "01265262", "카카오뱅크"),
    ("373220", "01515323", "LG에너지솔루션"),
    ("247540", "00942976", "에코프로비엠"),
]

DART_REPORT_TYPES = [
    ("A", "earnings_release", "분기보고서"),
    ("B", "dividend", "현금배당 결정"),
    ("D", "buyback_announcement", "자기주식 취득결정"),
]

NEWS_OUTLETS = ["hankyung", "edaily", "chosunbiz", "seoulfn"]
KIND_EVENTS = [
    ("trading_halt", "suspension", "매매거래정지"),
    ("mgmt_issue", "watchlist_designation", "관리종목 지정"),
    ("disclosure_violation", "unfaithful_disclosure", "불성실공시"),
]
NOTE_TYPES = ["thesis", "journal", "conviction", "note"]


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _yaml_quote(s: str) -> str:
    """Minimal YAML double-quoting — escapes backslashes and double-quotes."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _dart_body(rng: random.Random, ticker: str, name: str, report_type: str) -> str:
    """Plausible Korean DART text body 200-2000 chars."""
    paragraphs = [
        f"{name}({ticker})는 {report_type}을(를) 공시하였다.",
        f"매출액은 전년 동기 대비 {rng.randint(1, 30)}% 변동하였으며, "
        f"영업이익은 {rng.randint(1000, 99999)}억원 수준이다.",
        "본 공시는 자본시장과 금융투자업에 관한 법률에 따라 작성되었으며, "
        "투자판단의 참고자료로 활용 가능하다.",
        f"주요 사업 부문별 실적은 반도체 {rng.randint(10, 80)}%, "
        f"디스플레이 {rng.randint(5, 30)}%로 구성된다.",
        "본 보고서는 외부감사인의 검토를 거쳤다.",
    ]
    target_chars = rng.randint(220, 1800)
    out: list[str] = []
    while sum(len(p) for p in out) < target_chars:
        out.append(rng.choice(paragraphs))
    return "\n\n".join(out)


def _news_body(rng: random.Random, ticker: str, name: str) -> str:
    paragraphs = [
        f"{name}({ticker})의 주가가 외국인 매수세에 힘입어 강세를 보이고 있다.",
        "증권가에서는 실적 개선 기대감이 반영된 결과로 분석한다.",
        f'한 증권사 연구원은 "{name}의 영업이익률이 {rng.randint(5, 25)}%대로 회복될 가능성이 높다"고 평가하였다.',
        "업계에서는 향후 분기 실적 발표를 주목하고 있다.",
        f"이날 거래량은 평소 대비 {rng.randint(120, 250)}% 증가하였다.",
    ]
    target_chars = rng.randint(220, 900)
    out: list[str] = []
    while sum(len(p) for p in out) < target_chars:
        out.append(rng.choice(paragraphs))
    return "\n\n".join(out)


def _kind_body(rng: random.Random, ticker: str, name: str, kind_label: str) -> str:
    return (
        f"한국거래소는 {name}({ticker})에 대해 {kind_label} 조치를 통보하였다. "
        f"사유: 투자유의 환기. 적용 기간 {rng.randint(1, 30)}일. "
        "해당 조치는 거래소 공시규정에 근거한다."
    ) * 2


def _note_body(rng: random.Random, name: str, note_type: str) -> str:
    return (
        f"# {name} {note_type} 메모\n\n"
        f"오늘 자체 분석 결과 {name}의 향후 {rng.randint(3, 12)}개월 전망에 대해 "
        f"{rng.choice(['긍정적', '중립적', '부정적'])} 의견을 가진다.\n\n"
        f"리스크: 환율, 경쟁심화, 수요둔화. 보유 비중 조정은 {rng.choice(['확대', '유지', '축소'])}.\n"
    )


def _write_md(
    path: Path,
    *,
    fm_lines: list[str],
    body: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "---\n" + "\n".join(fm_lines) + "\n---\n" + body + "\n"
    path.write_text(content, encoding="utf-8")


def _build_dart_doc(
    rng: random.Random,
    out_root: Path,
    ticker: str,
    corp_code: str,
    name: str,
    report_type: str,
    event_type: str,
    label: str,
    seq: int,
) -> Path:
    rcept_no = f"2026{seq:08d}"
    body = _dart_body(rng, ticker, name, label)
    content_hash = _sha256_hex(body)
    fetched_at = "2026-04-01T09:00:00+00:00"
    summary = f"{name} {label} 요약 — {ticker}"
    fm_lines = [
        "provenance:",
        "  source: dart",
        f'  source_id: "{rcept_no}"',
        f'  source_url: "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"',
        '  date: "2026-04-01"',
        f'  fetched_at: "{fetched_at}"',
        f'  content_hash: "{content_hash}"',
        f'  corp_code: "{corp_code}"',
        f'  ticker: "{ticker}"',
        f'  company_name: "{_yaml_quote(name)}"',
        '  lang: "ko"',
        '  trust_level: "trusted"',
        "ingest_state:",
        "  processed: false",
        "  injection_flags: []",
        "_derived:",
        f'  tickers: ["{ticker}"]',
        f'  event_type: "{event_type}"',
        "  catalysts: []",
        "  numeric_facts: []",
        f'  summary: "{_yaml_quote(summary)}"',
    ]
    path = out_root / "raw" / "dart" / "2026-04-01" / f"{ticker}-{rcept_no}.md"
    _write_md(path, fm_lines=fm_lines, body=body)
    return path


def _build_news_doc(
    rng: random.Random,
    out_root: Path,
    ticker: str,
    corp_code: str,
    name: str,
    seq: int,
) -> Path:
    outlet = NEWS_OUTLETS[seq % len(NEWS_OUTLETS)]
    body = _news_body(rng, ticker, name)
    content_hash = _sha256_hex(body)
    slug = f"{outlet}-{seq:04d}-{ticker}"
    summary = f"{name} 뉴스 요약 #{seq}"
    fm_lines = [
        "provenance:",
        "  source: news",
        f'  source_id: "{slug}"',
        f'  source_url: "https://news.example.invalid/{slug}"',
        '  date: "2026-04-01"',
        '  fetched_at: "2026-04-01T08:30:00+00:00"',
        f'  content_hash: "{content_hash}"',
        f'  corp_code: "{corp_code}"',
        f'  ticker: "{ticker}"',
        f'  outlet: "{outlet}"',
        '  license_flag: "summary_only"',
        '  lang: "ko"',
        '  trust_level: "semi_trusted"',
        "ingest_state:",
        "  processed: false",
        "  injection_flags: []",
        "_derived:",
        f'  tickers: ["{ticker}"]',
        '  event_type: "macro_commentary"',
        "  catalysts: []",
        "  numeric_facts: []",
        f'  summary: "{_yaml_quote(summary)}"',
    ]
    path = out_root / "raw" / "news" / "2026-04-01" / f"{slug}.md"
    _write_md(path, fm_lines=fm_lines, body=body)
    return path


def _build_kind_doc(
    rng: random.Random,
    out_root: Path,
    ticker: str,
    corp_code: str,
    name: str,
    kind_event: tuple[str, str, str],
    seq: int,
) -> Path:
    kind_id, event_type, kind_label = kind_event
    body = _kind_body(rng, ticker, name, kind_label)
    content_hash = _sha256_hex(body)
    slug = f"{kind_id}-{seq:04d}-{ticker}"
    summary = f"{name} {kind_label}"
    fm_lines = [
        "provenance:",
        "  source: kind",
        f'  source_id: "{slug}"',
        f'  source_url: "https://kind.krx.co.kr/{slug}"',
        '  date: "2026-04-01"',
        '  fetched_at: "2026-04-01T07:00:00+00:00"',
        f'  content_hash: "{content_hash}"',
        f'  corp_code: "{corp_code}"',
        f'  ticker: "{ticker}"',
        '  lang: "ko"',
        '  trust_level: "trusted"',
        "ingest_state:",
        "  processed: false",
        "  injection_flags: []",
        "_derived:",
        f'  tickers: ["{ticker}"]',
        f'  event_type: "{event_type}"',
        "  catalysts: []",
        "  numeric_facts: []",
        f'  summary: "{_yaml_quote(summary)}"',
    ]
    path = out_root / "raw" / "kind" / "2026-04-01" / f"{slug}.md"
    _write_md(path, fm_lines=fm_lines, body=body)
    return path


def _build_note_doc(
    rng: random.Random,
    out_root: Path,
    ticker: str,
    name: str,
    note_type: str,
    seq: int,
) -> Path:
    body = _note_body(rng, name, note_type)
    slug = f"memo-{seq:03d}-{ticker}"
    fm_lines = [
        f'type: "{note_type}"',
        f'tickers: ["{ticker}"]',
        "  ",  # placeholder removed below
    ]
    # Build NoteFrontmatter-shaped block directly (NoteFrontmatter is a flat
    # schema, not nested under provenance).
    fm_lines = [
        f'type: "{note_type}"',
        f'tickers: ["{ticker}"]',
        "tags: []",
        "  ".strip(),
        'created: "2026-04-01T09:00:00+09:00"',
        'updated: "2026-04-01T09:00:00+09:00"',
        'author: "yamin"',
    ]
    fm_lines = [line for line in fm_lines if line]
    path = out_root / "notes" / f"{slug}.md"
    _write_md(path, fm_lines=fm_lines, body=body)
    return path


def _build_portfolio(out_root: Path) -> Path:
    holdings = TICKERS[:3]
    watchlist = [t[0] for t in TICKERS[3:]]
    lines = ["holdings:"]
    avg_costs = [70000, 130000, 40000]
    qtys = [100, 50, 30]
    for (ticker, _cc, _name), qty, avg_cost in zip(holdings, qtys, avg_costs, strict=True):
        lines.append(f'  - ticker: "{ticker}"')
        lines.append(f"    qty: {qty}")
        lines.append(f"    avg_cost: {avg_cost}")
    lines.append("watchlist:")
    for t in watchlist:
        lines.append(f'  - "{t}"')
    body = "Test portfolio for MCP-10 CI gates. Synthetic positions only.\n"
    path = out_root / "notes" / "private" / "portfolio.md"
    _write_md(path, fm_lines=lines, body=body)
    return path


def _build_heartbeat(out_root: Path) -> Path:
    fm_lines = [
        'updated_at: "2026-04-26T18:00:00+09:00"',
        "sources:",
        '  dart: { last_success: "2026-04-26T17:30:00+09:00", last_error: null }',
        '  krx: { last_success: "2026-04-26T17:35:00+09:00", last_error: null }',
        '  news: { last_success: "2026-04-26T17:50:00+09:00", last_error: null }',
        '  macro: { last_success: "2026-04-26T17:00:00+09:00", last_error: null }',
        '  kind: { last_success: "2026-04-26T17:45:00+09:00", last_error: null }',
    ]
    path = out_root / "ingested" / "_status" / "heartbeat.md"
    _write_md(path, fm_lines=fm_lines, body="<!-- auto-generated test heartbeat -->")
    return path


def _build_readme(out_root: Path) -> Path:
    text = (
        "# mcp-vault test fixture\n\n"
        "**Auto-generated by** `scripts/build_mcp_vault_fixture.py`. "
        "Manual edits will be lost on the next regeneration.\n\n"
        "Used by Phase 6 Plan 06-03 (CI gate fixture corpus, MCP-10).\n\n"
        "Synthetic data only — corp_codes/qty/avg_cost are not real positions.\n"
    )
    path = out_root / "README.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def build(out_root: Path, clean: bool) -> dict[str, int]:
    if clean and out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    rng = random.Random(42)

    counts = {"dart": 0, "news": 0, "kind": 0, "notes": 0}

    seq = 1
    # DART: 3 reports per ticker = 30 docs.
    for ticker, corp_code, name in TICKERS:
        for report_id, event_type, label in DART_REPORT_TYPES:
            _build_dart_doc(
                rng, out_root, ticker, corp_code, name, report_id, event_type, label, seq
            )
            seq += 1
            counts["dart"] += 1

    # News: 4 per ticker = 40 docs.
    seq = 1
    for ticker, corp_code, name in TICKERS:
        for _ in range(4):
            _build_news_doc(rng, out_root, ticker, corp_code, name, seq)
            seq += 1
            counts["news"] += 1

    # KIND: 20 across half the tickers (5 tickers × 4 events).
    seq = 1
    for ticker, corp_code, name in TICKERS[:5]:
        for i in range(4):
            event = KIND_EVENTS[i % len(KIND_EVENTS)]
            _build_kind_doc(rng, out_root, ticker, corp_code, name, event, seq)
            seq += 1
            counts["kind"] += 1

    # Notes: 10 across 5 tickers (2 each, varying type).
    seq = 1
    for ticker, _corp_code, name in TICKERS[:5]:
        for i in range(2):
            note_type = NOTE_TYPES[(seq - 1) % len(NOTE_TYPES)]
            _build_note_doc(rng, out_root, ticker, name, note_type, seq)
            seq += 1
            counts["notes"] += 1

    _build_portfolio(out_root)
    _build_heartbeat(out_root)
    _build_readme(out_root)

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Build mcp-vault test fixture corpus.")
    parser.add_argument("--out", required=True, help="Output dir (e.g. tests/fixtures/mcp-vault)")
    parser.add_argument("--clean", action="store_true", help="rm -rf the output dir first")
    args = parser.parse_args()

    out = Path(args.out)
    counts = build(out, clean=args.clean)
    total = sum(counts.values())
    print(f"Built {total} docs at {out}: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
