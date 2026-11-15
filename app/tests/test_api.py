"""API 오류 형식과 요청 메트릭. DB 함수는 가짜로 바꿔서 DB 없이 돌린다.

TestClient를 with 없이 쓰면 lifespan(풀 열기, 수집 시작)이 실행되지 않는다.
"""

from datetime import datetime, timezone
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient

import api
import db
import main

T = datetime(2026, 11, 15, 1, 20, 30, tzinfo=timezone.utc)
ROW = {
    "market_code": "KRW-BTC",
    "korean_name": "비트코인",
    "trade_price": Decimal("143250000.00000000"),
    "change_rate": Decimal("0.012300"),
    "acc_trade_volume_24h": Decimal("1234.50000000"),
    "exchange_ts": T,
    "collected_at": T,
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(db, "is_active_market", lambda m: m == "KRW-BTC")
    monkeypatch.setattr(db, "latest_prices", lambda: [ROW])
    monkeypatch.setattr(db, "latest_price", lambda m: ROW)
    monkeypatch.setattr(db, "price_history", lambda m, s, e, limit: [ROW])
    monkeypatch.setattr(api.status, "current_status", lambda: ("OK", T))
    return TestClient(main.app, raise_server_exceptions=False)


def test_prices_shape(client):
    body = client.get("/api/v1/prices").json()
    assert body["collector"] == {"status": "OK", "last_success_at": "2026-11-15T01:20:30Z", "stale": False}
    assert body["items"][0]["trade_price"] == "143250000.00000000"  # 문자열
    assert body["items"][0]["collected_at"] == "2026-11-15T01:20:30Z"


def test_stale_when_delayed(client, monkeypatch):
    monkeypatch.setattr(api.status, "current_status", lambda: ("DELAYED", T))
    res = client.get("/api/v1/prices")
    assert res.status_code == 200  # 수집 실패는 오류 응답이 아니다
    assert res.json()["collector"]["stale"] is True


def test_unknown_market_is_404(client):
    res = client.get("/api/v1/prices/KRW-NOPE")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "MARKET_NOT_FOUND"


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=1001", "limit=abc", "from=yesterday",
     "from=2026-11-15T02:00:00Z&to=2026-11-15T01:00:00Z"],
)
def test_invalid_parameter_is_400(client, query):
    res = client.get(f"/api/v1/prices/KRW-BTC/history?{query}")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_PARAMETER"


def test_history_ok(client):
    res = client.get("/api/v1/prices/KRW-BTC/history?from=2026-11-15T00:00:00Z&limit=10")
    assert res.status_code == 200
    assert res.json()["items"][0]["trade_price"] == "143250000.00000000"


def test_db_down_is_503(client, monkeypatch):
    def down():
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(db, "latest_prices", down)
    res = client.get("/api/v1/prices")
    assert res.status_code == 503
    assert res.json() == {"error": {"code": "DB_UNAVAILABLE", "message": "DB에 연결할 수 없습니다"}}


def test_unexpected_error_is_500(client, monkeypatch):
    def boom():
        raise RuntimeError("bug")

    monkeypatch.setattr(db, "latest_prices", boom)
    res = client.get("/api/v1/prices")
    assert res.status_code == 500
    assert res.json()["error"]["code"] == "INTERNAL_ERROR"


def test_unknown_path_uses_error_format(client):
    res = client.get("/nope")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_health_does_not_touch_db(client, monkeypatch):
    def down():
        raise psycopg.OperationalError("down")

    monkeypatch.setattr(db, "ping", down)
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 503


def requests_count(path, status):
    return main.HTTP_REQUESTS_TOTAL.labels(path=path, status=status)._value.get()


def test_metrics_use_route_template(client):
    before = requests_count("/api/v1/prices/{market}", "404")
    client.get("/api/v1/prices/KRW-NOPE")
    assert requests_count("/api/v1/prices/{market}", "404") == before + 1


def test_metrics_count_500(client, monkeypatch):
    monkeypatch.setattr(db, "latest_prices", lambda: 1 / 0)
    before = requests_count("/api/v1/prices", "500")
    client.get("/api/v1/prices")
    assert requests_count("/api/v1/prices", "500") == before + 1


def test_metrics_endpoint(client):
    text = client.get("/metrics").text
    assert 'collector_fetch_total{reason="timeout",result="fail"}' in text
