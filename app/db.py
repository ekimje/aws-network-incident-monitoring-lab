"""PostgreSQL 접근. SQL은 모두 이 파일에 모은다.

연결은 커넥션 풀로 재사용한다. 요청마다 새로 연결하면 부하 테스트 때 DB 연결 수가 먼저 바닥난다.
DB에 닿지 않으면 풀에서 연결을 얻다가 psycopg.OperationalError(PoolTimeout 포함)가 난다.
API는 이 예외를 503 DB_UNAVAILABLE로 바꾸고(main.py), 수집기는 db_error로 센다(collector.py).
"""

from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

import config

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

pool = ConnectionPool(
    config.DB_CONNINFO,
    min_size=1,
    max_size=config.DB_POOL_MAX_SIZE,
    timeout=3,  # 풀에서 연결을 3초 안에 못 받으면 실패
    kwargs={"row_factory": dict_row},  # 결과 행을 dict로 받는다
    check=ConnectionPool.check_connection,  # DB가 재시작됐을 때 끊긴 연결을 걸러낸다
    open=False,  # main.py의 lifespan에서 연다
)


# --- 스키마 -----------------------------------------------------------
def ensure_schema():
    with pool.connection() as conn:
        conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def ping():
    with pool.connection() as conn:
        conn.execute("SELECT 1")


# --- 수집 -------------------------------------------------------------
def get_active_market_codes():
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT market_code FROM markets WHERE is_active ORDER BY market_code"
        ).fetchall()
    return [row["market_code"] for row in rows]


def save_success_run(started_at, finished_at, http_status, duration_ms, ticks):
    """성공한 수집 1회를 저장하고, 새로 저장된 시세 행 수를 돌려준다.

    collect_runs 1행과 price_ticks 여러 행을 한 트랜잭션으로 저장한다.
    같은 (market_code, exchange_ts) 시세는 거래가 없어 값이 안 바뀐 경우라 건너뛴다.
    """
    with pool.connection() as conn:  # with 블록이 정상 종료되면 commit, 예외면 rollback
        run_id = conn.execute(
            """
            INSERT INTO collect_runs (started_at, finished_at, result, http_status, duration_ms)
            VALUES (%s, %s, 'SUCCESS', %s, %s)
            RETURNING id
            """,
            (started_at, finished_at, http_status, duration_ms),
        ).fetchone()["id"]

        saved = 0
        for tick in ticks:
            cur = conn.execute(
                """
                INSERT INTO price_ticks
                    (market_code, run_id, trade_price, change_rate,
                     acc_trade_volume_24h, exchange_ts, collected_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (market_code, exchange_ts) DO NOTHING
                """,
                (
                    tick["market"], run_id, tick["trade_price"], tick["change_rate"],
                    tick["acc_trade_volume_24h"], tick["exchange_ts"], finished_at,
                ),
            )
            saved += cur.rowcount

        conn.execute("UPDATE collect_runs SET saved_count = %s WHERE id = %s", (saved, run_id))
    return saved


def save_failed_run(started_at, finished_at, reason, http_status, duration_ms):
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO collect_runs (started_at, finished_at, result, reason, http_status, duration_ms)
            VALUES (%s, %s, 'FAIL', %s, %s, %s)
            """,
            (started_at, finished_at, reason, http_status, duration_ms),
        )


def delete_expired(price_retention_days, run_retention_days):
    """보관 기간이 지난 행을 지운다. 시세를 먼저 지워야 수집 이력의 FK(RESTRICT)에 걸리지 않는다."""
    with pool.connection() as conn:
        ticks = conn.execute(
            "DELETE FROM price_ticks WHERE collected_at < now() - make_interval(days => %s)",
            (price_retention_days,),
        ).rowcount
        runs = conn.execute(
            "DELETE FROM collect_runs WHERE started_at < now() - make_interval(days => %s)",
            (run_retention_days,),
        ).rowcount
    return ticks, runs


# --- 수집 상태 --------------------------------------------------------
def recent_success_times(limit):
    """최근 성공한 수집의 종료 시각, 최신순."""
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT finished_at FROM collect_runs
            WHERE result = 'SUCCESS'
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [row["finished_at"] for row in rows]


def first_run_started_at():
    with pool.connection() as conn:
        row = conn.execute("SELECT min(started_at) AS first FROM collect_runs").fetchone()
    return row["first"]


def last_failure():
    with pool.connection() as conn:
        return conn.execute(
            """
            SELECT finished_at, reason, http_status FROM collect_runs
            WHERE result = 'FAIL'
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()


def count_failures_since(minutes):
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT count(*) AS n FROM collect_runs
            WHERE result = 'FAIL' AND started_at >= now() - make_interval(mins => %s)
            """,
            (minutes,),
        ).fetchone()
    return row["n"]


# --- 조회 -------------------------------------------------------------
def list_active_markets():
    with pool.connection() as conn:
        return conn.execute(
            """
            SELECT market_code, korean_name, english_name
            FROM markets WHERE is_active
            ORDER BY market_code
            """
        ).fetchall()


def is_active_market(market_code):
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM markets WHERE market_code = %s AND is_active", (market_code,)
        ).fetchone()
    return row is not None


# 코인별 최신 시세 1행. LATERAL로 코인마다 인덱스(market_code, collected_at DESC)를 타고 1행만 읽는다.
_LATEST_PRICES_SQL = """
    SELECT m.market_code, m.korean_name,
           t.trade_price, t.change_rate, t.acc_trade_volume_24h, t.exchange_ts, t.collected_at
    FROM markets m
    JOIN LATERAL (
        SELECT * FROM price_ticks p
        WHERE p.market_code = m.market_code
        ORDER BY p.collected_at DESC
        LIMIT 1
    ) t ON true
    WHERE m.is_active {extra}
    ORDER BY m.market_code
"""


def latest_prices():
    with pool.connection() as conn:
        return conn.execute(_LATEST_PRICES_SQL.format(extra="")).fetchall()


def latest_price(market_code):
    with pool.connection() as conn:
        return conn.execute(
            _LATEST_PRICES_SQL.format(extra="AND m.market_code = %s"), (market_code,)
        ).fetchone()


def price_history(market_code, start, end, limit):
    """기간 안의 시세를 최신순으로 limit개. start·end가 None이면 그쪽 경계는 두지 않는다."""
    with pool.connection() as conn:
        return conn.execute(
            """
            SELECT trade_price, change_rate, acc_trade_volume_24h, exchange_ts, collected_at
            FROM price_ticks
            WHERE market_code = %(market)s
              AND (%(start)s::timestamptz IS NULL OR collected_at >= %(start)s)
              AND (%(end)s::timestamptz IS NULL OR collected_at <= %(end)s)
            ORDER BY collected_at DESC
            LIMIT %(limit)s
            """,
            {"market": market_code, "start": start, "end": end, "limit": limit},
        ).fetchall()
