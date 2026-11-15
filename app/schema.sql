-- 테이블 정의는 docs/erd.md를 따른다.
-- 앱이 시작할 때마다 실행되므로 모든 문장은 여러 번 실행해도 결과가 같아야 한다 (IF NOT EXISTS, ON CONFLICT).

CREATE TABLE IF NOT EXISTS markets (
    market_code  varchar(20) PRIMARY KEY,
    korean_name  varchar(50) NOT NULL,
    english_name varchar(50),
    is_active    boolean     NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS collect_runs (
    id          bigserial   PRIMARY KEY,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    result      varchar(10) NOT NULL,
    reason      varchar(20),
    http_status smallint,
    duration_ms integer,
    saved_count integer     NOT NULL DEFAULT 0,
    CONSTRAINT collect_runs_result_check
        CHECK (result IN ('SUCCESS', 'FAIL')),
    CONSTRAINT collect_runs_reason_check
        CHECK (reason IN ('timeout', 'connect_error', 'http_error', 'parse_error')),
    -- 성공이면 reason은 비어 있고, 실패면 반드시 있어야 한다
    CONSTRAINT collect_runs_reason_required
        CHECK ((result = 'SUCCESS' AND reason IS NULL) OR (result = 'FAIL' AND reason IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS collect_runs_started_at_idx
    ON collect_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS price_ticks (
    id                   bigserial     PRIMARY KEY,
    market_code          varchar(20)   NOT NULL REFERENCES markets (market_code) ON DELETE RESTRICT,
    run_id               bigint        NOT NULL REFERENCES collect_runs (id) ON DELETE RESTRICT,
    trade_price          numeric(20,8) NOT NULL,
    change_rate          numeric(10,6),
    acc_trade_volume_24h numeric(30,8),
    exchange_ts          timestamptz   NOT NULL,
    collected_at         timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT price_ticks_market_exchange_ts_key UNIQUE (market_code, exchange_ts)
);

CREATE INDEX IF NOT EXISTS price_ticks_market_collected_at_idx
    ON price_ticks (market_code, collected_at DESC);

-- 수집 대상 초기값. 이미 있는 코인은 건드리지 않는다 (is_active를 바꿔 둔 경우 유지).
-- 이름은 업비트 /v1/market/all 응답 기준이며, 코인 개수는 아직 열린 질문이다.
INSERT INTO markets (market_code, korean_name, english_name) VALUES
    ('KRW-BTC',  '비트코인',       'Bitcoin'),
    ('KRW-ETH',  '이더리움',       'Ethereum'),
    ('KRW-XRP',  '엑스알피(리플)', 'XRP'),
    ('KRW-SOL',  '솔라나',         'Solana'),
    ('KRW-DOGE', '도지코인',       'Dogecoin')
ON CONFLICT (market_code) DO NOTHING;
