"""수집 실패 사유 분류. 장애 원인 판별의 근거라 사유별로 확인한다."""

from decimal import Decimal

import httpx
import pytest

import collector
from collector import FetchError, fetch_tickers, parse_tickers

MARKETS = ["KRW-BTC", "KRW-ETH"]

TICKER = {
    "market": "KRW-BTC",
    "trade_price": 143250000.0,
    "signed_change_rate": -0.0123,
    "change_rate": 0.0123,
    "acc_trade_volume_24h": 1234.56789012,
    "timestamp": 1794705629000,
}


def client_with(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def reason_of(handler):
    with pytest.raises(FetchError) as e, client_with(handler) as client:
        data, status = fetch_tickers(client, MARKETS)
        parse_tickers(data, MARKETS, status)
    return e.value.reason, e.value.http_status


# --- fetch_tickers ----------------------------------------------------
def test_success_returns_json_and_status():
    with client_with(lambda req: httpx.Response(200, json=[TICKER])) as client:
        data, status = fetch_tickers(client, MARKETS)
    assert status == 200 and data == [TICKER]


def test_sends_markets_param():
    seen = {}

    def handler(request):
        seen["markets"] = request.url.params["markets"]
        return httpx.Response(200, json=[TICKER])

    with client_with(handler) as client:
        fetch_tickers(client, MARKETS)
    assert seen["markets"] == "KRW-BTC,KRW-ETH"


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("no response", request=request)

    assert reason_of(handler) == ("timeout", None)


def test_connect_timeout_is_timeout():
    def handler(request):
        raise httpx.ConnectTimeout("no syn-ack", request=request)

    assert reason_of(handler) == ("timeout", None)


def test_connect_error():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    assert reason_of(handler) == ("connect_error", None)


@pytest.mark.parametrize("status", [404, 429, 500, 503])
def test_http_error(status):
    assert reason_of(lambda req: httpx.Response(status, text="error")) == ("http_error", status)


def test_non_json_is_parse_error():
    assert reason_of(lambda req: httpx.Response(200, text="<html>")) == ("parse_error", 200)


# --- parse_tickers ----------------------------------------------------
def test_parse_extracts_fields():
    [tick] = parse_tickers([TICKER], MARKETS)
    assert tick["market"] == "KRW-BTC"
    assert tick["trade_price"] == Decimal("143250000.0")
    assert tick["change_rate"] == Decimal("-0.0123")  # 부호 있는 값
    assert tick["acc_trade_volume_24h"] == Decimal("1234.56789012")
    assert tick["exchange_ts"].isoformat() == "2026-11-15T01:20:29+00:00"


@pytest.mark.parametrize(
    "data",
    [
        [],  # 빈 목록
        {"error": "x"},  # 목록이 아님
        [{"market": "KRW-BTC", "korean_name": "비트코인"}],  # /v1/market/all 같은 다른 응답
        [{**TICKER, "trade_price": None}],  # 빈 값
        [{**TICKER, "trade_price": 0}],  # 0원
        [{**TICKER, "timestamp": "abc"}],
        [{**TICKER, "market": "KRW-NOPE"}],  # 요청한 코인이 없음
    ],
)
def test_parse_error(data):
    with pytest.raises(FetchError) as e:
        parse_tickers(data, MARKETS, 200)
    assert e.value.reason == "parse_error"


# --- collect_once: 결과가 DB와 메트릭에 남는지 ---------------------------
def counter(result, reason):
    return collector.COLLECTOR_FETCH_TOTAL.labels(result=result, reason=reason)._value.get()


def test_collect_once_records_failure(monkeypatch):
    saved = {}
    monkeypatch.setattr(collector.db, "get_active_market_codes", lambda: MARKETS)
    monkeypatch.setattr(
        collector.db, "save_failed_run",
        lambda started, finished, reason, status, ms: saved.update(reason=reason, status=status),
    )
    before = counter("fail", "http_error")

    with client_with(lambda req: httpx.Response(429, text="Too Many Requests")) as client:
        collector.collect_once(client)

    assert saved == {"reason": "http_error", "status": 429}
    assert counter("fail", "http_error") == before + 1


def test_collect_once_records_success(monkeypatch):
    saved = {}
    monkeypatch.setattr(collector.db, "get_active_market_codes", lambda: MARKETS)

    def fake_save(started, finished, status, ms, ticks):
        saved["ticks"] = ticks
        return len(ticks)

    monkeypatch.setattr(collector.db, "save_success_run", fake_save)
    before = counter("success", "none")

    with client_with(lambda req: httpx.Response(200, json=[TICKER])) as client:
        collector.collect_once(client)

    assert len(saved["ticks"]) == 1
    assert counter("success", "none") == before + 1
    assert collector.COLLECTOR_LAST_SUCCESS._value.get() > 0
