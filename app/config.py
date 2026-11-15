"""환경변수로 바꿀 수 있는 설정을 한곳에 모은다.

장애 재현도 대부분 여기 값을 바꾸고 컨테이너를 다시 띄우는 방식으로 한다.
"""

import os


def _float(name, default):
    return float(os.environ.get(name, default))


def _int(name, default):
    return int(os.environ.get(name, default))


# --- DB ---------------------------------------------------------------
DB_CONNINFO = (
    f"host={os.environ.get('DB_HOST', 'localhost')} "
    f"port={os.environ.get('DB_PORT', '5432')} "
    f"dbname={os.environ.get('DB_NAME', 'prices')} "
    f"user={os.environ.get('DB_USER', 'app')} "
    f"password={os.environ.get('DB_PASSWORD', '')} "
    "connect_timeout=3"  # 3초 안에 연결되지 않으면 실패로 본다
)
# timestamptz는 DB 안에서 항상 UTC로 저장된다. 응답으로 내보낼 때 api.iso()가 UTC로 바꾼다.
DB_POOL_MAX_SIZE = _int("DB_POOL_MAX_SIZE", 10)

# --- 수집 -------------------------------------------------------------
# 수집 주기 (초). 상태 판정(DELAYED·FAILED)도 이 값의 배수로 계산한다.
COLLECT_INTERVAL_SECONDS = _float("COLLECT_INTERVAL_SECONDS", 10)

# 외부 API 주소. 장애 재현 때 바꾼다.
#   - 외부 API 장애(http_error): UPBIT_TICKER_PATH=/v1/ticker-wrong  → 404
#   - 데이터 장애(parse_error):  UPBIT_TICKER_PATH=/v1/market/all   → 시세 필드가 없는 응답
UPBIT_BASE_URL = os.environ.get("UPBIT_BASE_URL", "https://api.upbit.com")
UPBIT_TICKER_PATH = os.environ.get("UPBIT_TICKER_PATH", "/v1/ticker")

# 외부 API 타임아웃 (초). 수집 주기보다 짧아야 다음 주기와 겹치지 않는다.
FETCH_TIMEOUT_SECONDS = _float("FETCH_TIMEOUT_SECONDS", 5)

# --- 수집 상태 판정 (docs/architecture.md 7.4) --------------------------
DELAYED_AFTER_INTERVALS = _float("DELAYED_AFTER_INTERVALS", 2)
FAILED_AFTER_INTERVALS = _float("FAILED_AFTER_INTERVALS", 4)
# 장애 뒤 몇 번 연속 성공하면 RECOVERED → OK로 볼지
RECOVERY_SUCCESS_STREAK = _int("RECOVERY_SUCCESS_STREAK", 3)

# --- 보관 정책 (docs/erd.md 3장) ---------------------------------------
PRICE_RETENTION_DAYS = _int("PRICE_RETENTION_DAYS", 7)
RUN_RETENTION_DAYS = _int("RUN_RETENTION_DAYS", 30)

# --- 장애 주입 --------------------------------------------------------
# 앱 장애(5xx 급증) 재현용. /api/v1 요청 중 이 비율만큼 일부러 예외를 낸다. 평소에는 0.
FAULT_API_ERROR_RATE = _float("FAULT_API_ERROR_RATE", 0)
