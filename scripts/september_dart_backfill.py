"""Collect portfolio A/B filings for September 1-23, 2026 with full pagination.

Run from the repo root. Uses the existing full-body extractor and DB writer.
The private report contains source receipt IDs for reconciliation, never API keys.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sqlalchemy import text

from collectors.dart.db_writer import upsert_dart_filing
from collectors.dart.fetcher import DartDocumentError, fetch_body
from db.engine import get_engine
from db.entity import resolve_entities
from shared.portfolio import Portfolio
from shared.run_log import record_collector_run

START = "20260901"
END = "20260923"
REPORT = Path("notes/private/september-dart-report.json")


def fetch_attachment_notice(session: requests.Session, receipt: str) -> tuple[str, str]:
    """Read a public correction notice when the XML API has no file (014).

    Preserve attachment links; linked PDF/image contents are not extracted.
    """
    time.sleep(1)
    response = session.get(
        "https://dart.fss.or.kr/dsaf001/main.do", params={"rcpNo": receipt}, timeout=30
    )
    response.raise_for_status()
    match = re.search(r'viewDoc\("' + receipt + r'",\s*"(\d+)",\s*"0"', response.text)
    if not match:
        raise ValueError("DART viewer document identifier missing")
    time.sleep(1)
    viewer = session.get(
        "https://dart.fss.or.kr/report/viewer.do",
        params={
            "rcpNo": receipt,
            "dcmNo": match[1],
            "eleId": "0",
            "offset": "0",
            "length": "0",
            "dtd": "dart4.xsd",
        },
        timeout=30,
    )
    viewer.raise_for_status()
    viewer.encoding = "utf-8"
    soup = BeautifulSoup(viewer.text, "html.parser")
    for node in soup(["script", "style"]):
        node.decompose()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(viewer.url, anchor["href"])
        if href.startswith("https://dart.fss.or.kr/"):
            anchor.replace_with(f"{anchor.get_text(' ', strip=True)} ({href})")
    body = soup.get_text(" ", strip=True)
    if "정 정 신 고" not in body or len(body) < 100:
        raise ValueError("Unexpected attachment correction notice")
    return body, viewer.url


def main() -> int:
    load_dotenv(".env")
    # Exceptions from requests may include credential-bearing URLs.
    logging.getLogger("collectors.dart.fetcher").setLevel(logging.CRITICAL)
    engine = get_engine()
    scope = Portfolio.load(Path(".")).scope_tickers()
    entities = resolve_entities(engine, scope)
    if len(entities) != len(scope):
        raise RuntimeError("Portfolio entity mappings incomplete")
    by_corp = {entity.corp_code: ticker for ticker, entity in entities.items()}
    report = {
        "start": START,
        "end": END,
        "scope_count": len(scope),
        "pages": [],
        "receipts": [],
        "body_missing": [],
        "attachment_notices": [],
        "stats": {"total": 0, "inserted": 0, "updated": 0, "skipped": 0, "failed": []},
    }
    stats = report["stats"]
    started = time.monotonic()

    def checkpoint() -> None:
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    selected = {}
    session = requests.Session()
    for category in ("A", "B"):
        page = 1
        while True:
            payload = None
            for attempt in range(3):
                time.sleep(1 + attempt * 2)
                try:
                    response = session.get(
                        "https://opendart.fss.or.kr/api/list.json",
                        params={
                            "crtfc_key": os.environ["DART_API_KEY"],
                            "bgn_de": START,
                            "end_de": END,
                            "last_reprt_at": "Y",
                            "pblntf_ty": category,
                            "page_count": 100,
                            "page_no": page,
                            "sort": "date",
                            "sort_mth": "asc",
                        },
                        timeout=30,
                    )
                    if response.status_code != 200:
                        raise RuntimeError(f"HTTP_{response.status_code}")
                    payload = response.json()
                    if payload.get("status") not in ("000", "013"):
                        raise RuntimeError("DART_" + str(payload.get("status")))
                    break
                except Exception as exc:
                    if attempt == 2:
                        stats["failed"].append(
                            {"doc": f"list:{category}:{page}", "error": type(exc).__name__}
                        )
                        payload = None
            if payload is None:
                break
            rows = payload.get("list", [])
            report["pages"].append(
                {
                    "category": category,
                    "page": page,
                    "total_count": payload.get("total_count", 0),
                    "total_page": payload.get("total_page", 0),
                    "returned": len(rows),
                }
            )
            for row in rows:
                if row["corp_code"] in by_corp and START <= row["rcept_dt"] <= END:
                    selected[row["rcept_no"]] = {**row, "category": category}
            print(f"DART list {category} page={page} selected={len(selected)}", flush=True)
            checkpoint()
            if page >= int(payload.get("total_page", 0)):
                break
            page += 1

    report["receipts"] = sorted(selected)
    report["listing_complete"] = not stats["failed"]
    stats["total"] = len(selected)
    checkpoint()
    for index, receipt in enumerate(sorted(selected), 1):
        row = selected[receipt]
        try:
            time.sleep(1)
            source_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"
            try:
                body = fetch_body(SimpleNamespace(rcept_no=receipt))
            except DartDocumentError as exc:
                if "status=014" not in str(exc):
                    raise
                body, source_url = fetch_attachment_notice(session, receipt)
                report["attachment_notices"].append(
                    {
                        "receipt": receipt,
                        "source_url": source_url,
                        "limitation": (
                            "Notice text and links stored; "
                            "attachment PDF/image contents not extracted"
                        ),
                    }
                )
            if not body:
                report["body_missing"].append(receipt)
                stats["failed"].append({"doc": receipt, "error": "document_unavailable"})
                continue
            filed_at = datetime.strptime(row["rcept_dt"], "%Y%m%d").replace(
                hour=15, minute=30, tzinfo=ZoneInfo("Asia/Seoul")
            )
            outcome = upsert_dart_filing(
                engine,
                rcept_no=receipt,
                corp_code=row["corp_code"],
                ticker=by_corp[row["corp_code"]],
                filed_at=filed_at,
                report_nm=row["report_nm"],
                pblntf_ty=row["category"],
                body_md=body,
                source_url=source_url,
            )
            stats[outcome] += 1
        except Exception as exc:
            stats["failed"].append({"doc": receipt, "error": type(exc).__name__})
        finally:
            print(
                f"DART body {index}/{len(selected)} inserted={stats['inserted']} "
                f"failed={len(stats['failed'])}",
                flush=True,
            )
            checkpoint()

    with engine.connect() as connection:
        stored = (
            set(
                connection.execute(
                    text(
                        "SELECT rcept_no FROM filings "
                        "WHERE rcept_no = ANY(:ids) AND length(body_md)>0"
                    ),
                    {"ids": sorted(selected)},
                ).scalars()
            )
            if selected
            else set()
        )
    report["missing_receipts_in_db"] = sorted(set(selected) - stored)
    report["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    record_collector_run(
        engine,
        "dart",
        stats,
        report["elapsed_ms"],
        extra={
            "start": START,
            "end": END,
            "scope_count": len(scope),
            "full_pagination": report["listing_complete"],
            "attachment_notices": report["attachment_notices"],
            "missing_receipts": report["missing_receipts_in_db"],
        },
    )
    checkpoint()
    print(json.dumps(stats, ensure_ascii=False), flush=True)
    return 1 if stats["failed"] or report["missing_receipts_in_db"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
