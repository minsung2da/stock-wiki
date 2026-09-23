"""Read-only explorer tests against a disposable migrated PostgreSQL database."""

from __future__ import annotations

import json
from http.client import HTTPConnection
from threading import Thread

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError

from db.explorer import DATASETS, Explorer, Filters, make_server


@pytest.fixture
def explorer(pg_clean):
    with pg_clean.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (corp_code, canonical_name, current_ticker) "
                "VALUES ('00126380', '삼성전자', '005930')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO news (url_hash, url, outlet, tickers, published_at, "
                "title, content_hash, body_md) VALUES "
                "(:hash, :url, '테스트', ARRAY['005930'], :published, :title, "
                ":hash, :body)"
            ),
            [
                dict(
                    hash=str(i) * 64,
                    url=f"https://example.com/{i}",
                    published=stamp,
                    title=title,
                    body="저장된 본문 CaseSensitive <script>alert(1)</script>\n" + "가" * 5000,
                )
                for i, stamp, title in [
                    (1, "2026-09-22T14:59:59Z", "전일 기사"),
                    (2, "2026-09-22T15:00:00Z", "반도체 경계 기사"),
                    (3, "2026-09-23T14:59:59Z", "반도체 마감 기사"),
                    (4, "2026-09-23T15:00:00Z", "익일 기사"),
                ]
            ],
        )
        conn.execute(
            text(
                "INSERT INTO fundamentals "
                "(ticker, fdate, per, dividend_yield, dps, source) VALUES "
                "('005930', '2026-09-23', 12.3456, 2.1234, 1444.0000, 'fundamentals')"
            )
        )
    return Explorer(pg_clean)


@pytest.mark.parametrize(
    "values",
    [
        {"dataset": "news;DROP TABLE news"},
        {"sql": "SELECT 1"},
        {"page": "0"},
        {"page_size": "101"},
        {"start": "2026-02-30"},
        {"start": "2026-09-24", "end": "2026-09-23"},
        {"ticker": "12"},
    ],
)
def test_reject_invalid_filters(values):
    with pytest.raises(ValueError):
        Filters.model_validate(values)


def test_inventory_and_kst_filters(explorer):
    inventory = {row["id"]: row for row in explorer.inventory()}
    assert inventory["news"]["count"] == 4
    assert inventory["filings"]["count"] == 0
    filters = Filters(
        dataset="news",
        q="삼성전자",
        ticker="005930",
        start="2026-09-23",
        end="2026-09-23",
        page_size=1,
    )
    first = explorer.search(filters)
    assert first["total"] == 2
    assert first["rows"][0]["title"] == "반도체 마감 기사"
    second = explorer.search(filters.model_copy(update={"page": 2}))
    assert second["rows"][0]["title"] == "반도체 경계 기사"
    assert first["rows"][0]["_key"] != second["rows"][0]["_key"]
    detail = explorer.detail("news", first["rows"][0]["_key"])
    assert len(detail["body_md"]) > 5000
    assert "<script>" in detail["body_md"]
    assert explorer.search(Filters(dataset="news", q="' OR 1=1 --"))["total"] == 0
    assert explorer.search(Filters(dataset="news", q="%"))["total"] == 0
    assert explorer.search(Filters(dataset="news", q="저장된 본문"))["total"] == 0
    assert (
        explorer.search(Filters(dataset="news", q="저장된 본문", include_body=True))["total"] == 4
    )
    assert (
        explorer.search(Filters(dataset="news", q="CaseSensitive", include_body=True))["total"] == 4
    )
    assert (
        explorer.search(Filters(dataset="news", q="casesensitive", include_body=True))["total"] == 0
    )


def test_exact_numbers_and_composite_key(explorer):
    result = explorer.search(Filters(dataset="fundamentals", q="삼성전자"))
    assert result["total"] == 1
    detail = explorer.detail("fundamentals", result["rows"][0]["_key"])
    assert detail["per"] == "12.3456"
    assert detail["dividend_yield"] == "2.1234"
    assert detail["dps"] == "1444.0000"
    assert explorer.detail("fundamentals", '["000000","2026-09-23"]') is None
    with pytest.raises(ValueError):
        explorer.detail("fundamentals", '["005930"]')


def test_database_enforces_read_only(explorer):
    with pytest.raises(DBAPIError), explorer.connection() as conn:
        assert conn.execute(text("SHOW transaction_read_only")).scalar() == "on"
        conn.execute(text("DELETE FROM news"))
    assert explorer.search(Filters(dataset="news"))["total"] == 4


def test_all_allowlisted_queries_match_migrated_schema(explorer):
    for dataset, spec in DATASETS.items():
        result = explorer.search(Filters(dataset=dataset))
        assert result["total"] >= 0
        assert explorer.detail(dataset, json.dumps(["nonexistent"] * len(spec.keys))) is None
        for row in result["rows"]:
            assert explorer.detail(dataset, row["_key"]) is not None


def test_http_routes_and_boundary(explorer, monkeypatch):
    server = make_server(explorer, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = f"127.0.0.1:{server.server_port}"

    def request(path, method="GET", headers=None):
        client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        client.request(method, path, headers=headers or {})
        response = client.getresponse()
        data = response.read()
        result = response.status, response.getheaders(), data
        client.close()
        return result

    try:
        status, headers, body = request("/")
        assert status == 200 and "데이터 탐색기" in body.decode()
        assert dict(headers)["Content-Security-Policy"]
        assert request("/api/inventory")[0] == 200
        status, _, body = request("/api/search?dataset=news")
        assert status == 200 and json.loads(body)["total"] == 4
        assert request("/api/search?dataset=news&sql=DELETE")[0] == 400
        assert request("/api/search?dataset=news&dataset=ohlcv")[0] == 400
        assert request("/api/search?dataset=unknown")[0] == 400
        assert request("/api/search?dataset=macro_series&ticker=005930")[0] == 400
        assert request("/api/inventory", "POST")[0] == 405
        assert request("/api/inventory", headers={"Host": "evil.example"})[0] == 403
        assert request("/api/inventory", headers={"Origin": "https://evil.example"})[0] == 403
        assert request("/api/inventory", headers={"Origin": f"http://{host}"})[0] == 200
        assert request("/api/inventory", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
        assert request("/missing")[0] == 404

        def unavailable(_filters):
            raise OperationalError("SELECT secret", {}, Exception("password=hidden"))

        monkeypatch.setattr(explorer, "search", unavailable)
        status, _, body = request("/api/search?dataset=news")
        assert status == 503
        assert b"password" not in body and b"SELECT" not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
