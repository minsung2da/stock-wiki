"""Loopback-only, read-only browser for the explicitly supported stock datasets."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from db.engine import get_engine

KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class Dataset:
    label: str
    description: str
    columns: str
    keys: tuple[str, ...]
    preview: tuple[str, ...]
    search: tuple[str, ...]
    date_column: str | None = None
    timestamp: bool = False
    ticker_column: str | None = None
    corp_column: str | None = "corp_code"


# Identifiers below are code constants, never request inputs. Vector/token index
# internals are intentionally omitted; complete narratives remain in details.
DATASETS = {
    "filings": Dataset(
        "공시",
        "DART 공시 원문과 접수 정보",
        "rcept_no corp_code ticker filed_at report_nm pblntf_ty event_type source_url "
        "content_hash body_md fetched_at first_seen_at last_seen_at",
        ("rcept_no",),
        ("filed_at", "ticker", "report_nm", "pblntf_ty"),
        ("report_nm", "body_md", "rcept_no"),
        "filed_at",
        True,
        "ticker",
    ),
    "news": Dataset(
        "뉴스",
        "수집 당시 저장된 기사 본문과 관련 종목",
        "id url_hash url outlet corp_code tickers published_at title content_hash body_md "
        "license_flag fetched_at first_seen_at last_seen_at",
        ("id",),
        ("published_at", "tickers", "title", "outlet"),
        ("title", "body_md", "outlet"),
        "published_at",
        True,
        "tickers",
    ),
    "ohlcv": Dataset(
        "시세 · 수급",
        "일별 가격·거래량·투자자 수급·공매도",
        "ticker trade_date open high low close volume trading_value foreign_net inst_net "
        "retail_net short_volume short_balance corp_code fetched_at",
        ("ticker", "trade_date"),
        ("trade_date", "ticker", "close", "volume", "foreign_net"),
        ("ticker",),
        "trade_date",
        False,
        "ticker",
    ),
    "fundamentals": Dataset(
        "재무지표",
        "PER·PBR·EPS·BPS·ROE·배당수익률·DPS",
        "ticker fdate per pbr eps bps roe dividend_yield dps corp_code source fetched_at",
        ("ticker", "fdate"),
        ("fdate", "ticker", "per", "pbr", "dividend_yield", "dps"),
        ("ticker", "source"),
        "fdate",
        False,
        "ticker",
    ),
    "macro_series": Dataset(
        "매크로",
        "ECOS·FRED 경제지표 관측값",
        "source series_id item_code obs_date value unit label cycle fetched_at",
        ("source", "series_id", "item_code", "obs_date"),
        ("obs_date", "label", "value", "unit", "source"),
        ("label", "series_id", "item_code", "source"),
        "obs_date",
        corp_column=None,
    ),
    "decision_cards": Dataset(
        "근거 카드 · 브리핑",
        "분석 결과와 일간·주간 브리핑, 만료·모순 포함",
        "card_id corp_code ticker report_type report_date generated_at as_of payload body_md "
        "status supersedes superseded_by expires_at schema_version",
        ("card_id",),
        ("generated_at", "ticker", "report_type", "status", "card_id"),
        ("card_id", "body_md", "payload", "report_type"),
        "generated_at",
        True,
        "ticker",
    ),
    "entities": Dataset(
        "기업",
        "기업명·종목코드·시장·업종 기준 정보",
        "corp_code canonical_name current_ticker sector market listed_at delisted_at",
        ("corp_code",),
        ("canonical_name", "current_ticker", "market", "sector"),
        ("canonical_name", "current_ticker", "corp_code", "sector"),
        ticker_column="current_ticker",
    ),
    "entity_aliases": Dataset(
        "기업 별칭",
        "기업 이름과 종목코드의 유효기간 이력",
        "id corp_code kind value valid_from valid_to created_at",
        ("id",),
        ("value", "kind", "corp_code", "valid_from", "valid_to"),
        ("value", "kind"),
        "valid_from",
    ),
    "notes": Dataset(
        "메모",
        "DB에 저장된 사용자 투자 근거 메모",
        "path corp_code content_md content_hash updated_at",
        ("path",),
        ("updated_at", "corp_code", "path"),
        ("path", "content_md"),
        "updated_at",
        True,
    ),
    "collector_runs": Dataset(
        "수집 실행 기록",
        "소스별 실행 시각·처리 건수·오류 통계",
        "id source run_at elapsed_ms stats extra",
        ("id",),
        ("run_at", "source", "elapsed_ms", "stats"),
        ("source", "stats", "extra"),
        "run_at",
        True,
        corp_column=None,
    ),
    "jev_reviews": Dataset(
        "JEV 검토 기록",
        "뉴스 기업 관련성·카드 인용 검토 (비교 기록 모드, 원본 판단 유지)",
        "review_id task subject_id input_hash model prompt_version mode status threshold "
        "input_payload result_payload request_id usage error_code created_at",
        ("review_id",),
        ("created_at", "task", "subject_id", "status", "result_payload"),
        ("task", "subject_id", "input_payload", "result_payload", "error_code"),
        "created_at",
        True,
        corp_column=None,
    ),
}
JSON_COLUMNS = {"payload", "stats", "extra", "input_payload", "result_payload", "usage"}
BODY_COLUMNS = {"body_md", "content_md"}
LABELS = {
    "filed_at": "공시 시각",
    "ticker": "종목코드",
    "report_nm": "공시 제목",
    "pblntf_ty": "공시 유형",
    "published_at": "발행 시각",
    "tickers": "관련 종목",
    "title": "기사 제목",
    "outlet": "매체",
    "trade_date": "거래일",
    "close": "종가",
    "volume": "거래량",
    "foreign_net": "외국인 순매수",
    "fdate": "기준일",
    "dividend_yield": "배당수익률 (%)",
    "dps": "DPS (원)",
    "per": "PER (배)",
    "pbr": "PBR (배)",
    "eps": "EPS (원)",
    "bps": "BPS (원)",
    "roe": "ROE",
    "obs_date": "관측일",
    "label": "지표명",
    "value": "값",
    "unit": "단위",
    "source": "출처",
    "generated_at": "생성 시각",
    "report_type": "보고서 유형",
    "status": "상태",
    "card_id": "카드 ID",
    "canonical_name": "기업명",
    "current_ticker": "현재 종목코드",
    "market": "시장",
    "sector": "업종",
    "kind": "별칭 유형",
    "corp_code": "기업코드",
    "valid_from": "유효 시작일",
    "valid_to": "유효 종료일",
    "updated_at": "갱신 시각",
    "path": "메모 경로",
    "run_at": "실행 시각",
    "elapsed_ms": "소요 시간 (ms)",
    "stats": "처리 통계",
    "body_md": "저장된 본문",
    "content_md": "메모 본문",
    "payload": "분석 구조화 결과",
    "fetched_at": "수집 시각",
    "source_url": "출처 URL",
    "url": "기사 URL",
    "expires_at": "만료 시각",
    "rcept_no": "접수번호",
    "extra": "추가 실행 정보",
    "review_id": "검토 ID",
    "task": "검토 종류",
    "subject_id": "검토 대상",
    "input_payload": "입력 근거·질문",
    "result_payload": "JEV 판정·검토 필요 여부",
    "error_code": "오류 코드",
    "created_at": "기록 시각",
    "threshold": "검토 분기 임계값",
    "model": "사용 모델",
    "usage": "API 사용량",
}


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset: str = "filings"
    q: str = Field(default="", max_length=200)
    include_body: bool = False
    ticker: str = Field(default="", pattern=r"^(?:[0-9A-Z]{6})?$")
    start: date | None = None
    end: date | None = None
    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=25, ge=1, le=100)

    @field_validator("dataset")
    @classmethod
    def known_dataset(cls, value: str) -> str:
        if value not in DATASETS:
            raise ValueError("지원하지 않는 데이터입니다.")
        return value

    @field_validator("start", "end", mode="before")
    @classmethod
    def iso_date(cls, value: object) -> object:
        if isinstance(value, str) and (len(value) != 10 or value[4] != "-" or value[7] != "-"):
            raise ValueError("날짜는 YYYY-MM-DD 형식입니다.")
        return value

    @model_validator(mode="after")
    def applicable_filters(self) -> Filters:
        spec = DATASETS[self.dataset]
        if self.start and self.end and self.start > self.end:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
        if (self.start or self.end) and not spec.date_column:
            raise ValueError("이 데이터는 날짜 필터를 지원하지 않습니다.")
        if self.ticker and not (spec.ticker_column or spec.corp_column):
            raise ValueError("이 데이터는 종목 필터를 지원하지 않습니다.")
        if self.include_body and not BODY_COLUMNS.intersection(spec.search):
            raise ValueError("이 데이터에는 본문 검색 필드가 없습니다.")
        if self.end == date.max:
            raise ValueError("지원 범위를 벗어난 종료일입니다.")
        return self


def serializable(value: Any) -> Any:
    """Preserve NUMERIC precision and avoid JS's unsafe large integer range."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(KST).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int) and abs(value) > 2**53 - 1:
        return str(value)
    if isinstance(value, Mapping):
        return {key: serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(item) for item in value]
    return value


def entity_relation(spec: Dataset) -> str:
    relations = []
    if spec.corp_column:
        relations.append(f"e.corp_code = d.{spec.corp_column}")
    if spec.ticker_column == "tickers":
        relations.append("e.current_ticker = ANY(d.tickers)")
    elif spec.ticker_column:
        relations.append(f"e.current_ticker = d.{spec.ticker_column}")
    return " OR ".join(relations)


class Explorer:
    def __init__(self, engine: Engine):
        self.engine = engine

    @contextmanager
    def connection(self, *, include_body: bool = False) -> Iterator[Connection]:
        with self.engine.connect() as conn, conn.begin():
            conn.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            timeout = "30000ms" if include_body else "5000ms"
            conn.execute(text(f"SET LOCAL statement_timeout = '{timeout}'"))
            yield conn

    def inventory(self) -> list[dict[str, Any]]:
        result = []
        with self.connection() as conn:
            for name, spec in DATASETS.items():
                latest = f"max({spec.date_column})" if spec.date_column else "NULL"
                row = (
                    conn.execute(text(f"SELECT count(*) AS count, {latest} AS latest FROM {name}"))
                    .mappings()
                    .one()
                )
                result.append(
                    {
                        "id": name,
                        "label": spec.label,
                        "description": spec.description,
                        "count": row["count"],
                        "latest": serializable(row["latest"]),
                        "date_column": spec.date_column,
                        "ticker_filter": bool(spec.ticker_column or spec.corp_column),
                        "body_search": bool(BODY_COLUMNS.intersection(spec.search)),
                        "columns": [
                            {"key": key, "label": LABELS.get(key, key)} for key in spec.preview
                        ],
                    }
                )
        return result

    def search(self, filters: Filters) -> dict[str, Any]:
        spec = DATASETS[filters.dataset]
        conditions: list[str] = []
        params: dict[str, Any] = {}
        relation = entity_relation(spec)
        if filters.q.strip():
            # LIKE wildcards are literal user text, not a hidden query language.
            escaped = (
                filters.q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            params["q"] = f"%{escaped}%"
            expressions = [
                f"CAST(d.{col} AS text) {'LIKE' if col in BODY_COLUMNS else 'ILIKE'} :q"
                for col in spec.search
                if filters.include_body or col not in BODY_COLUMNS
            ]
            if relation:
                expressions.append(
                    f"EXISTS (SELECT 1 FROM entities e WHERE ({relation}) "
                    "AND e.canonical_name ILIKE :q)"
                )
            conditions.append("(" + " OR ".join(expressions) + ")")
        if filters.ticker:
            params["ticker"] = filters.ticker
            if spec.ticker_column == "tickers":
                conditions.append(":ticker = ANY(d.tickers)")
            elif spec.ticker_column:
                conditions.append(f"d.{spec.ticker_column} = :ticker")
            else:
                conditions.append(
                    f"EXISTS (SELECT 1 FROM entities e WHERE ({relation}) "
                    "AND e.current_ticker = :ticker)"
                )
        for name, value, operator in (("start", filters.start, ">="), ("end", filters.end, "<")):
            if value is not None:
                boundary = value + timedelta(days=1) if name == "end" else value
                params[name] = (
                    datetime.combine(boundary, time.min, KST) if spec.timestamp else boundary
                )
                conditions.append(f"d.{spec.date_column} {operator} :{name}")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        order = [f"d.{spec.date_column} DESC NULLS LAST"] if spec.date_column else []
        order += [f"d.{key} DESC" for key in spec.keys]
        columns = tuple(dict.fromkeys((*spec.keys, *spec.preview)))
        select = ", ".join(
            f"CAST(d.{col} AS text) AS {col}" if col in JSON_COLUMNS else f"d.{col}"
            for col in columns
        )
        with self.connection(include_body=filters.include_body) as conn:
            total = conn.execute(
                text(f"SELECT count(*) FROM {filters.dataset} d{where}"), params
            ).scalar_one()
            rows = (
                conn.execute(
                    text(
                        f"SELECT {select} FROM {filters.dataset} d{where} "
                        f"ORDER BY {', '.join(order)} LIMIT :limit OFFSET :offset"
                    ),
                    {
                        **params,
                        "limit": filters.page_size,
                        "offset": (filters.page - 1) * filters.page_size,
                    },
                )
                .mappings()
                .all()
            )
        output = []
        for row in rows:
            item = self._row(row)
            item["_key"] = json.dumps([str(item[key]) for key in spec.keys], ensure_ascii=False)
            output.append(item)
        return {
            "dataset": filters.dataset,
            "total": total,
            "page": filters.page,
            "page_size": filters.page_size,
            "rows": output,
        }

    @staticmethod
    def _row(row: Mapping[Any, Any]) -> dict[str, Any]:
        result = dict(row)
        for key in JSON_COLUMNS & result.keys():
            if result[key] is not None:
                result[key] = json.loads(result[key], parse_float=Decimal)
        return {key: serializable(value) for key, value in result.items()}

    def detail(self, dataset: str, key: str) -> dict[str, Any] | None:
        if dataset not in DATASETS or len(key) > 4096:
            raise ValueError("잘못된 데이터 또는 레코드 키입니다.")
        spec = DATASETS[dataset]
        values = json.loads(key)
        if (
            not isinstance(values, list)
            or len(values) != len(spec.keys)
            or not all(isinstance(v, str) for v in values)
        ):
            raise ValueError("잘못된 레코드 키입니다.")
        where = " AND ".join(f"CAST({col} AS text) = :k{i}" for i, col in enumerate(spec.keys))
        columns = ", ".join(
            f"CAST({col} AS text) AS {col}" if col in JSON_COLUMNS else col
            for col in spec.columns.split()
        )
        with self.connection() as conn:
            row = (
                conn.execute(
                    text(f"SELECT {columns} FROM {dataset} WHERE {where}"),
                    {f"k{i}": value for i, value in enumerate(values)},
                )
                .mappings()
                .first()
            )
        return self._row(row) if row else None


def make_server(explorer: Explorer, port: int = 8766) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "StockExplorer"
        sys_version = ""

        def log_message(self, format: str, *args: Any) -> None:
            # Do not log searches or notes in URLs.
            return

        def reply(self, status: int, value: Any, html: bool = False) -> None:
            body = (
                value.encode("utf-8")
                if html
                else json.dumps(value, ensure_ascii=False).encode("utf-8")
            )
            self.send_response(status)
            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8" if html else "application/json; charset=utf-8",
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            server = cast(ThreadingHTTPServer, self.server)
            authority = f"127.0.0.1:{server.server_port}"
            hosts = {authority, f"localhost:{server.server_port}"}
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if (
                host not in hosts
                or (origin is not None and origin != f"http://{host}")
                or self.headers.get("Sec-Fetch-Site") == "cross-site"
            ):
                self.reply(403, {"error": "로컬 탐색기에서만 접근할 수 있습니다."})
                return
            if len(self.path) > 8192:
                self.reply(400, {"error": "요청이 너무 깁니다."})
                return
            parsed = urlsplit(self.path)
            try:
                query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=12)
                if any(len(values) != 1 for values in query.values()):
                    raise ValueError("중복 필터입니다.")
                params = {key: values[0] for key, values in query.items()}
                if parsed.path == "/" and not params:
                    self.reply(
                        200,
                        Path(__file__).with_suffix(".html").read_text(encoding="utf-8"),
                        html=True,
                    )
                elif parsed.path == "/api/inventory" and not params:
                    self.reply(200, {"datasets": explorer.inventory(), "labels": LABELS})
                elif parsed.path == "/api/search":
                    self.reply(200, explorer.search(Filters.model_validate(params)))
                elif parsed.path == "/api/detail" and set(params) == {"dataset", "key"}:
                    result = explorer.detail(params["dataset"], params["key"])
                    self.reply(
                        200 if result else 404,
                        result if result else {"error": "레코드를 찾을 수 없습니다."},
                    )
                else:
                    self.reply(404, {"error": "지원하지 않는 경로입니다."})
            except ValueError:
                self.reply(
                    400,
                    {
                        "error": "필터를 확인해 주세요. 날짜·종목코드·페이지 값 또는 "
                        "요청 형식이 올바르지 않습니다."
                    },
                )
            except SQLAlchemyError:
                logging.warning("Explorer database query failed")
                self.reply(
                    503,
                    {
                        "error": "DB 조회에 실패했습니다. PostgreSQL 연결과 "
                        "마이그레이션 상태를 확인한 뒤 다시 시도해 주세요."
                    },
                )

        def do_POST(self) -> None:
            self.reply(405, {"error": "조회 전용입니다. GET 요청만 지원합니다."})

        do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_POST

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local read-only stock database explorer")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    engine = get_engine()
    server = make_server(Explorer(engine), port=args.port)
    print(f"Stock database explorer: http://127.0.0.1:{args.port} (read-only)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        engine.dispose()


if __name__ == "__main__":
    main()
