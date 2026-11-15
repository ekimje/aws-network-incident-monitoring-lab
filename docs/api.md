# API 명세

> 관련 문서: [아키텍처 설계](architecture.md) · [데이터 모델(ERD)](erd.md)

외부 API는 `/api/v1` 아래에 조회 전용으로 두고, 운영용 엔드포인트는 ALB로 노출하지 않는다. 수집이 멈춰도 조회는 200으로 응답하고, 데이터가 오래됐다는 사실은 `stale` 필드로 알린다.

## 1. 엔드포인트

| 메서드 | 경로 | 설명 | 노출 |
| --- | --- | --- | --- |
| GET | `/api/v1/markets` | 수집 대상 코인 목록 | ALB |
| GET | `/api/v1/prices` | 전체 코인의 최신 시세 + 수집 상태 | ALB |
| GET | `/api/v1/prices/{market}` | 코인 하나의 최신 시세 | ALB |
| GET | `/api/v1/prices/{market}/history` | 기간별 시세 이력. `from`, `to`, `limit`(기본 100, 최대 1000) | ALB |
| GET | `/api/v1/collector/status` | 수집 상태, 마지막 성공 시각, 최근 실패 사유 | ALB |
| GET | `/` | 프론트 HTML | ALB |
| GET | `/health` | 프로세스 생존 확인 (ALB 헬스 체크용) | ALB 헬스 체크만 |
| GET | `/ready` | DB 연결까지 확인 | 내부 |
| GET | `/metrics` | Prometheus 메트릭 | 내부 (모니터링 EC2 보안 그룹만 허용) |

ALB 리스너 규칙은 `/api/*`와 `/`만 앱으로 보내고, 나머지는 404를 반환한다.

## 2. 응답 예시

`GET /api/v1/prices` (숫자는 형식 예시)

```json
{
  "collector": {
    "status": "OK",
    "last_success_at": "2026-11-15T01:20:30Z",
    "stale": false
  },
  "items": [
    {
      "market": "KRW-BTC",
      "korean_name": "비트코인",
      "trade_price": "0",
      "change_rate": "0.0123",
      "acc_trade_volume_24h": "0",
      "exchange_ts": "2026-11-15T01:20:29Z",
      "collected_at": "2026-11-15T01:20:30Z"
    }
  ]
}
```

`GET /api/v1/collector/status`

```json
{
  "status": "FAILED",
  "last_success_at": "2026-11-15T01:10:00Z",
  "last_failure": {
    "at": "2026-11-15T01:20:30Z",
    "reason": "timeout",
    "http_status": null
  },
  "failures_last_10m": 20
}
```

- 가격·비율은 문자열로 내보내 `numeric` 정밀도를 유지한다.
- `status`는 [수집 상태](architecture.md#74-수집-상태)(OK·DELAYED·FAILED·RECOVERED)를 그대로 쓴다. DELAYED 이상이면 `stale`은 `true`다.

## 3. 오류 응답

모든 오류는 같은 형식을 쓴다: `{"error": {"code": "MARKET_NOT_FOUND", "message": "..."}}`

| HTTP | code | 상황 |
| --- | --- | --- |
| 400 | `INVALID_PARAMETER` | `from`/`to` 형식 오류, `limit` 범위 초과 |
| 404 | `MARKET_NOT_FOUND` | 수집 대상에 없는 마켓 코드 |
| 503 | `DB_UNAVAILABLE` | DB 연결 실패 (`/ready`도 503) |
| 500 | `INTERNAL_ERROR` | 그 외 예상하지 못한 예외 |

수집 실패는 오류 응답이 아니다. 조회는 정상 동작하므로 200 + `stale: true`로 응답해야, 5xx 알림과 수집 알림이 섞이지 않는다.

## 4. 부하 테스트 시나리오

| 비중 | 요청 | 목적 |
| --- | --- | --- |
| 60% | `GET /api/v1/prices` | 기본 조회 부하 |
| 25% | `GET /api/v1/prices/{market}` | 코인별 조회 |
| 10% | `GET /api/v1/prices/{market}/history` | DB 조회 부하 |
| 5% | `GET /api/v1/prices/KRW-NOPE` | 404 지표가 0이 아닌 현실적인 기준선 |
