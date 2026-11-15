"""Collector: 주기마다 업비트 시세를 받아 DB에 저장하고, 결과를 메트릭과 collect_runs에 남긴다.

실패 사유(reason)는 장애 원인을 가르는 핵심이라 기준을 고정해 둔다 (docs/architecture.md 5.1).

    timeout        응답이 제한 시간 안에 오지 않음      → 방화벽 drop을 먼저 의심
    connect_error  DNS 실패, 연결 거부·끊김             → 네트워크 경로
    http_error     응답은 왔지만 4xx·5xx (429 포함)      → 외부 API
    parse_error    응답은 200인데 내용을 쓸 수 없음      → 데이터
    db_error       시세는 받았지만 DB에 저장하지 못함    → 앱·DB (메트릭에만 남는다. DB에 못 쓰므로)
"""

import logging
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import psycopg

import config
import db
from metrics import COLLECTOR_FETCH_DURATION, COLLECTOR_FETCH_TOTAL, COLLECTOR_LAST_SUCCESS

logger = logging.getLogger("collector")

CLEANUP_EVERY_SECONDS = 24 * 60 * 60


class FetchError(Exception):
    """수집 실패. reason은 collect_runs.reason, 메트릭 reason 레이블과 같은 값이다."""

    def __init__(self, reason, http_status=None, detail=""):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.http_status = http_status


def utcnow():
    return datetime.now(timezone.utc)


# --- 외부 API 호출 ----------------------------------------------------
def fetch_tickers(client, market_codes):
    """업비트 /v1/ticker 호출. (응답 JSON, HTTP 상태 코드)를 돌려주고, 실패하면 FetchError."""
    url = config.UPBIT_BASE_URL + config.UPBIT_TICKER_PATH
    try:
        response = client.get(url, params={"markets": ",".join(market_codes)})
    except httpx.TimeoutException as e:  # 연결·읽기 타임아웃 모두
        raise FetchError("timeout", detail=repr(e)) from e
    except httpx.TransportError as e:  # DNS 실패, 연결 거부, 연결 끊김 등
        raise FetchError("connect_error", detail=repr(e)) from e

    if response.status_code >= 400:
        raise FetchError("http_error", response.status_code, response.text[:200])

    try:
        return response.json(), response.status_code
    except ValueError as e:
        raise FetchError("parse_error", response.status_code, "JSON이 아님") from e


def parse_tickers(data, market_codes, http_status=None):
    """업비트 응답에서 저장할 필드만 뽑는다. 하나라도 쓸 수 없으면 전체를 parse_error로 본다.

    - change_rate는 부호가 있는 signed_change_rate를 쓴다 (업비트 change_rate는 절댓값)
    - exchange_ts는 업비트 timestamp(ms)를 UTC 시각으로 바꾼 값
    """
    if not isinstance(data, list) or not data:
        raise FetchError("parse_error", http_status, "시세 목록이 비어 있거나 목록이 아님")

    wanted = set(market_codes)
    ticks = []
    try:
        for item in data:
            if item["market"] not in wanted:
                continue
            trade_price = _decimal(item["trade_price"])
            if trade_price <= 0:
                raise ValueError(f"trade_price가 0 이하: {trade_price}")
            ticks.append({
                "market": item["market"],
                "trade_price": trade_price,
                "change_rate": _decimal_or_none(item.get("signed_change_rate")),
                "acc_trade_volume_24h": _decimal_or_none(item.get("acc_trade_volume_24h")),
                "exchange_ts": datetime.fromtimestamp(item["timestamp"] / 1000, tz=timezone.utc),
            })
    except (KeyError, TypeError, ValueError, ArithmeticError) as e:
        raise FetchError("parse_error", http_status, repr(e)) from e

    if not ticks:
        raise FetchError("parse_error", http_status, "요청한 코인이 응답에 없음")
    return ticks


def _decimal(value):
    # float를 바로 Decimal로 바꾸면 이진 오차가 따라오므로 문자열을 거친다
    d = Decimal(str(value))
    if not d.is_finite():
        raise ValueError(f"숫자가 아님: {value}")
    return d


def _decimal_or_none(value):
    return None if value is None else _decimal(value)


# --- 수집 1회 ---------------------------------------------------------
def collect_once(client):
    started_at = utcnow()

    try:
        market_codes = db.get_active_market_codes()
    except psycopg.Error:
        logger.exception("수집 대상 조회 실패 (DB)")
        COLLECTOR_FETCH_TOTAL.labels(result="fail", reason="db_error").inc()
        return
    if not market_codes:
        logger.warning("수집 대상 코인이 없음 (markets.is_active 확인)")
        return

    t0 = time.perf_counter()
    http_status = None
    try:
        try:
            data, http_status = fetch_tickers(client, market_codes)
        finally:
            COLLECTOR_FETCH_DURATION.observe(time.perf_counter() - t0)
        ticks = parse_tickers(data, market_codes, http_status)
    except FetchError as e:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.warning("수집 실패 reason=%s http_status=%s %s", e.reason, e.http_status, e)
        COLLECTOR_FETCH_TOTAL.labels(result="fail", reason=e.reason).inc()
        try:
            db.save_failed_run(started_at, utcnow(), e.reason, e.http_status, duration_ms)
        except psycopg.Error:
            logger.exception("수집 실패 이력 저장 실패 (DB)")
        return

    duration_ms = int((time.perf_counter() - t0) * 1000)
    try:
        saved = db.save_success_run(started_at, utcnow(), http_status, duration_ms, ticks)
    except psycopg.Error:
        logger.exception("시세 저장 실패 (DB)")
        COLLECTOR_FETCH_TOTAL.labels(result="fail", reason="db_error").inc()
        return

    COLLECTOR_FETCH_TOTAL.labels(result="success", reason="none").inc()
    COLLECTOR_LAST_SUCCESS.set(time.time())
    logger.info("수집 성공 markets=%d saved=%d duration_ms=%d", len(ticks), saved, duration_ms)


# --- 반복 실행 --------------------------------------------------------
def _prepare_db(stop):
    """스키마를 만들 때까지 재시도한다. DB가 늦게 떠도 앱은 죽지 않고 기다린다."""
    while not stop.is_set():
        try:
            db.ensure_schema()
            break
        except psycopg.Error:
            logger.exception("스키마 준비 실패, 5초 뒤 재시도")
            stop.wait(5)

    # 재시작 직후 마지막 성공 시각이 0으로 보여 알림이 잘못 뜨지 않게, DB 값으로 채워 둔다
    try:
        times = db.recent_success_times(1)
        if times:
            COLLECTOR_LAST_SUCCESS.set(times[0].timestamp())
    except psycopg.Error:
        logger.exception("마지막 성공 시각 조회 실패")


def _cleanup():
    try:
        ticks, runs = db.delete_expired(config.PRICE_RETENTION_DAYS, config.RUN_RETENTION_DAYS)
        logger.info("보관 기간 지난 행 삭제 price_ticks=%d collect_runs=%d", ticks, runs)
    except psycopg.Error:
        logger.exception("보관 기간 정리 실패")


def run_forever(stop):
    _prepare_db(stop)
    next_cleanup = time.monotonic()  # 시작하자마자 한 번 정리

    timeout = httpx.Timeout(config.FETCH_TIMEOUT_SECONDS)
    with httpx.Client(timeout=timeout, headers={"Accept": "application/json"}) as client:
        while not stop.is_set():
            cycle_start = time.monotonic()
            try:
                collect_once(client)
                if cycle_start >= next_cleanup:
                    _cleanup()
                    next_cleanup = cycle_start + CLEANUP_EVERY_SECONDS
            except Exception:
                # 예상하지 못한 예외가 나도 수집 스레드는 멈추지 않는다
                logger.exception("수집 루프 예외")
            # 수집에 걸린 시간을 빼고 기다려서, 시작 간격을 COLLECT_INTERVAL_SECONDS로 맞춘다
            elapsed = time.monotonic() - cycle_start
            stop.wait(max(0.0, config.COLLECT_INTERVAL_SECONDS - elapsed))


def start():
    """백그라운드 스레드로 수집을 시작하고, 멈출 때 쓸 Event를 돌려준다."""
    stop = threading.Event()
    threading.Thread(target=run_forever, args=(stop,), name="collector", daemon=True).start()
    return stop
