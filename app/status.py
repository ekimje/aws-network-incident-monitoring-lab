"""수집 상태 판정 (docs/architecture.md 7.4).

    OK ──(주기 2배 이상 성공 없음)──▶ DELAYED ──(4배 이상)──▶ FAILED
    DELAYED ──(성공)──▶ OK
    FAILED ──(성공)──▶ RECOVERED ──(연속 성공)──▶ OK

상태를 메모리에 들고 있지 않고, 매번 collect_runs의 성공 시각으로 다시 계산한다.
그래서 앱을 재시작해도 상태가 이어지고, 나중에 Collector와 API를 다른 컨테이너로 나눠도
API 쪽에서 같은 결과를 낼 수 있다. 상태의 근거(collect_runs)는 Collector만 쓴다.
"""

from datetime import datetime, timezone

import config
import db

OK = "OK"
DELAYED = "DELAYED"
FAILED = "FAILED"
RECOVERED = "RECOVERED"


def compute_status(now, success_times, first_run_at, interval,
                   delayed_after=2, failed_after=4, recovery_streak=3):
    """DB 없이 계산만 하는 함수 (테스트하기 쉽게 분리).

    success_times: 최근 성공 시각 목록, 최신순, recovery_streak개까지
    first_run_at:  첫 수집 시작 시각 (성공이 한 번도 없을 때만 쓴다). 수집 전이면 None
    """
    delayed_limit = delayed_after * interval
    failed_limit = failed_after * interval

    # 아직 한 번도 성공하지 못함: 첫 수집 시작부터 4배가 지나면 FAILED, 그 전에는 DELAYED
    if not success_times:
        if first_run_at is None:
            return DELAYED
        waited = (now - first_run_at).total_seconds()
        return FAILED if waited >= failed_limit else DELAYED

    since_last_success = (now - success_times[0]).total_seconds()
    if since_last_success >= failed_limit:
        return FAILED
    if since_last_success >= delayed_limit:
        return DELAYED

    # 최근 성공 사이에 4배 이상 벌어진 구간이 있으면, FAILED에서 돌아온 뒤
    # 아직 recovery_streak번 연속 성공하지 못한 것이다 → RECOVERED
    recent = success_times[:recovery_streak]
    for newer, older in zip(recent, recent[1:]):
        if (newer - older).total_seconds() >= failed_limit:
            return RECOVERED
    return OK


def is_stale(status):
    return status in (DELAYED, FAILED)


def current_status():
    """DB에서 근거를 읽어 지금 상태와 마지막 성공 시각을 돌려준다."""
    success_times = db.recent_success_times(config.RECOVERY_SUCCESS_STREAK)
    first_run_at = None if success_times else db.first_run_started_at()
    status = compute_status(
        now=datetime.now(timezone.utc),
        success_times=success_times,
        first_run_at=first_run_at,
        interval=config.COLLECT_INTERVAL_SECONDS,
        delayed_after=config.DELAYED_AFTER_INTERVALS,
        failed_after=config.FAILED_AFTER_INTERVALS,
        recovery_streak=config.RECOVERY_SUCCESS_STREAK,
    )
    last_success_at = success_times[0] if success_times else None
    return status, last_success_at
