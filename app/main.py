"""실시간 시세 수집·조회 서비스

- 15초마다 업비트에서 코인 현재가를 받아 PostgreSQL에 저장한다 (백그라운드 스레드)
- GET /        : 종목별 최신 시세를 HTML 표로 보여준다
- GET /health  : 서비스 상태
- GET /metrics : Prometheus 메트릭
"""

import json
import os
import threading
import time
import urllib.request
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

# ---------------------------------------------------------------
# 설정
# ---------------------------------------------------------------
MARKETS = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]
COLLECT_INTERVAL_SECONDS = 15
UPBIT_TICKER_URL = "https://api.upbit.com/v1/ticker?markets=" + ",".join(MARKETS)

# DB 접속 정보는 환경변수에서 읽는다 (.env 파일 참고)
DB_CONNINFO = (
    f"host={os.environ['DB_HOST']} "
    f"port={os.environ['DB_PORT']} "
    f"dbname={os.environ['DB_NAME']} "
    f"user={os.environ['DB_USER']} "
    f"password={os.environ['DB_PASSWORD']}"
)

# TODO(메트릭): 여기에 커스텀 메트릭을 정의한다
#   예) 수집 성공·실패 수(Counter), 마지막 갱신 시각(Gauge),
#       업비트 API 응답시간(Histogram), 남은 요청 수(Gauge)


# ---------------------------------------------------------------
# DB
# ---------------------------------------------------------------
def create_table():
    """앱 시작 시 prices 테이블이 없으면 만든다."""
    with psycopg.connect(DB_CONNINFO) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prices (
                id           SERIAL PRIMARY KEY,
                market       TEXT        NOT NULL,
                trade_price  NUMERIC     NOT NULL,
                collected_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def save_prices(tickers):
    """업비트 응답(종목 목록)을 prices 테이블에 저장한다."""
    with psycopg.connect(DB_CONNINFO) as conn:
        for ticker in tickers:
            conn.execute(
                "INSERT INTO prices (market, trade_price) VALUES (%s, %s)",
                (ticker["market"], ticker["trade_price"]),
            )
    # with 블록이 끝나면 자동으로 commit 된다


def get_latest_prices():
    """종목별로 가장 최근에 저장된 시세 한 줄씩 가져온다."""
    with psycopg.connect(DB_CONNINFO) as conn:
        # DISTINCT ON (market): 종목마다 첫 번째 행만 남긴다
        # ORDER BY ... collected_at DESC 이므로 첫 번째 행 = 가장 최근 시세
        return conn.execute(
            """
            SELECT DISTINCT ON (market) market, trade_price, collected_at
            FROM prices
            ORDER BY market, collected_at DESC
            """
        ).fetchall()


# ---------------------------------------------------------------
# 수집기
# ---------------------------------------------------------------
def fetch_tickers():
    """업비트 /v1/ticker에서 여러 종목 현재가를 한 번에 받아온다. (API 키 필요 없음)"""
    with urllib.request.urlopen(UPBIT_TICKER_URL, timeout=5) as response:
        # TODO(메트릭): 응답 헤더 Remaining-Req 에서 남은 요청 수를 읽어 Gauge로 기록
        return json.load(response)


def collect_forever():
    """15초마다 시세를 받아 DB에 저장한다. 백그라운드 스레드에서 계속 돈다."""
    while True:
        # TODO(에러 처리): 지금은 업비트 요청이나 DB 저장이 실패하면 예외가 나서
        #   이 스레드가 멈추고 수집이 끊긴다 (웹 화면과 /health는 계속 정상 응답).
        #   try/except로 감싸서 실패를 기록하고 다음 주기에 다시 시도하게 바꾼다.
        # TODO(메트릭): 수집 성공·실패 수, 응답시간, 마지막 갱신 시각을 여기서 기록
        tickers = fetch_tickers()
        save_prices(tickers)
        time.sleep(COLLECT_INTERVAL_SECONDS)


# ---------------------------------------------------------------
# 웹 (FastAPI)
# ---------------------------------------------------------------
@asynccontextmanager
async def lifespan(app):
    # 앱이 시작될 때 한 번 실행된다
    create_table()
    threading.Thread(target=collect_forever, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def index():
    rows = get_latest_prices()
    table_rows = "".join(
        f"<tr><td>{market}</td><td>{trade_price:,.0f}</td>"
        f"<td>{collected_at:%Y-%m-%d %H:%M:%S %Z}</td></tr>"
        for market, trade_price, collected_at in rows
    )
    return f"""
    <html>
      <head><meta charset="utf-8"><title>실시간 시세</title></head>
      <body>
        <h1>실시간 시세</h1>
        <table border="1" cellpadding="6">
          <tr><th>종목</th><th>현재가(원)</th><th>수집 시각</th></tr>
          {table_rows}
        </table>
      </body>
    </html>
    """


@app.get("/health")
def health():
    # TODO(헬스체크): DB에 SELECT 1을 날려서 실패하면 503을 반환하도록 바꾼다
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    # prometheus_client가 기본으로 모으는 메트릭(파이썬 프로세스 정보 등)을 그대로 내보낸다
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
