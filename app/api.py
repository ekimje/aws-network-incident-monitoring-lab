"""조회 API /api/v1 (docs/api.md).

조회는 외부 API를 부르지 않고 DB만 읽는다. 수집이 멈춰도 200으로 응답하고 stale로 알린다.
"""

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query

import config
import db
import status


class ApiError(Exception):
    """docs/api.md 3장 형식의 오류. main.py의 핸들러가 JSON으로 바꾼다."""

    def __init__(self, http_status, code, message):
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.message = message


def inject_fault():
    """앱 장애 재현용. FAULT_API_ERROR_RATE 비율만큼 일부러 예외를 내서 500을 만든다."""
    if config.FAULT_API_ERROR_RATE > 0 and random.random() < config.FAULT_API_ERROR_RATE:
        raise RuntimeError("FAULT_API_ERROR_RATE로 주입한 장애")


router = APIRouter(prefix="/api/v1", dependencies=[Depends(inject_fault)])


# --- 응답 변환 --------------------------------------------------------
def iso(value):
    """UTC 시각을 2026-11-15T01:20:30Z 형식으로. 화면에서 KST로 바꾼다."""
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def num(value):
    """numeric은 문자열로 내보내 정밀도를 지킨다. 'f' 형식이라 1E+8 같은 지수 표기가 나오지 않는다."""
    if value is None:
        return None
    return format(value, "f") if isinstance(value, Decimal) else str(value)


def price_item(row):
    return {
        "market": row["market_code"],
        "korean_name": row["korean_name"],
        "trade_price": num(row["trade_price"]),
        "change_rate": num(row["change_rate"]),
        "acc_trade_volume_24h": num(row["acc_trade_volume_24h"]),
        "exchange_ts": iso(row["exchange_ts"]),
        "collected_at": iso(row["collected_at"]),
    }


def collector_summary():
    current, last_success_at = status.current_status()
    return {
        "status": current,
        "last_success_at": iso(last_success_at),
        "stale": status.is_stale(current),
    }


def require_market(market):
    if not db.is_active_market(market):
        raise ApiError(404, "MARKET_NOT_FOUND", f"수집 대상이 아닌 마켓 코드: {market}")


def as_utc(value):
    """시간대가 없는 입력(2026-11-15T01:00:00)은 UTC로 본다."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


# --- 엔드포인트 -------------------------------------------------------
@router.get("/markets")
def list_markets():
    return {
        "items": [
            {
                "market": row["market_code"],
                "korean_name": row["korean_name"],
                "english_name": row["english_name"],
            }
            for row in db.list_active_markets()
        ]
    }


@router.get("/prices")
def list_prices():
    return {
        "collector": collector_summary(),
        "items": [price_item(row) for row in db.latest_prices()],
    }


@router.get("/prices/{market}")
def get_price(market: str):
    require_market(market)
    row = db.latest_price(market)
    return {
        "collector": collector_summary(),
        "item": price_item(row) if row else None,  # 수집 대상이지만 아직 시세가 없으면 null
    }


@router.get("/prices/{market}/history")
def get_price_history(
    market: str,
    start: datetime | None = Query(None, alias="from"),
    end: datetime | None = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
):
    start, end = as_utc(start), as_utc(end)
    if start and end and start > end:
        raise ApiError(400, "INVALID_PARAMETER", "from이 to보다 늦습니다")
    require_market(market)

    rows = db.price_history(market, start, end, limit)
    return {
        "market": market,
        "items": [
            {
                "trade_price": num(row["trade_price"]),
                "change_rate": num(row["change_rate"]),
                "acc_trade_volume_24h": num(row["acc_trade_volume_24h"]),
                "exchange_ts": iso(row["exchange_ts"]),
                "collected_at": iso(row["collected_at"]),
            }
            for row in rows
        ],
    }


@router.get("/collector/status")
def get_collector_status():
    current, last_success_at = status.current_status()
    failure = db.last_failure()
    return {
        "status": current,
        "last_success_at": iso(last_success_at),
        "last_failure": (
            {
                "at": iso(failure["finished_at"]),
                "reason": failure["reason"],
                "http_status": failure["http_status"],
            }
            if failure
            else None
        ),
        "failures_last_10m": db.count_failures_since(10),
    }
