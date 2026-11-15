"""Prometheus 메트릭 정의 (docs/architecture.md 5.2).

수집(collector_*)과 조회(http_*) 메트릭 이름을 나눠 두어,
나중에 Collector를 별도 컨테이너로 분리해도 대시보드·알림 규칙을 그대로 쓸 수 있게 한다.
"""

from prometheus_client import Counter, Gauge, Histogram

# --- 수집 -------------------------------------------------------------
# result: success | fail
# reason: none(성공) | timeout | connect_error | http_error | parse_error | db_error
COLLECTOR_FETCH_TOTAL = Counter(
    "collector_fetch_total",
    "수집 시도 결과와 실패 사유",
    ["result", "reason"],
)

COLLECTOR_FETCH_DURATION = Histogram(
    "collector_fetch_duration_seconds",
    "외부 시세 API 응답 시간 (실패한 호출 포함)",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 10),
)

COLLECTOR_LAST_SUCCESS = Gauge(
    "collector_last_success_timestamp",
    "마지막 수집 성공 시각 (unix 초)",
)

# --- 조회 -------------------------------------------------------------
# path는 실제 URL이 아니라 라우트 템플릿(/api/v1/prices/{market})을 쓴다.
# 실제 URL을 쓰면 KRW-NOPE 같은 값마다 시계열이 새로 생긴다.
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "조회 API 요청 수와 상태 코드",
    ["path", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "조회 API 지연 시간",
    ["path"],
)

# 처음부터 0으로 보이게 만들어 둔다. 한 번도 실패하지 않은 사유도 그래프·알림 식에서 0으로 잡힌다.
COLLECTOR_FETCH_TOTAL.labels(result="success", reason="none")
for _reason in ("timeout", "connect_error", "http_error", "parse_error", "db_error"):
    COLLECTOR_FETCH_TOTAL.labels(result="fail", reason=_reason)
