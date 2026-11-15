"""수집 상태 판정 (docs/architecture.md 7.4). 수집 주기 10초 기준: DELAYED 20초, FAILED 40초."""

from datetime import datetime, timedelta, timezone

from status import DELAYED, FAILED, OK, RECOVERED, compute_status, is_stale

NOW = datetime(2026, 11, 15, 1, 0, 0, tzinfo=timezone.utc)


def ago(seconds):
    return NOW - timedelta(seconds=seconds)


def status_of(success_seconds_ago, first_run_seconds_ago=None):
    first_run_at = None if first_run_seconds_ago is None else ago(first_run_seconds_ago)
    return compute_status(
        now=NOW,
        success_times=[ago(s) for s in success_seconds_ago],
        first_run_at=first_run_at,
        interval=10,
    )


def test_ok_when_recent_successes_are_regular():
    assert status_of([5, 15, 25]) == OK


def test_delayed_after_two_intervals():
    assert status_of([20, 30, 40]) == DELAYED


def test_failed_after_four_intervals():
    assert status_of([40, 50, 60]) == FAILED


def test_recovered_right_after_long_gap():
    # 방금 성공했지만 그 전 성공이 60초 전 → FAILED에서 돌아온 직후
    assert status_of([1, 60, 70]) == RECOVERED


def test_recovered_until_streak_reached():
    # 장애 뒤 두 번 성공 (3번 연속 성공 전)
    assert status_of([1, 11, 70]) == RECOVERED


def test_ok_after_streak_reached():
    # 장애 뒤 세 번 연속 성공 → 4번째 이전 간격은 보지 않는다
    assert status_of([1, 11, 21]) == OK


def test_short_gap_goes_back_to_ok_without_recovered():
    # DELAYED(20~40초)였다가 성공한 경우는 RECOVERED를 거치지 않는다
    assert status_of([1, 30, 40]) == OK


def test_no_runs_yet_is_delayed():
    assert status_of([], first_run_seconds_ago=None) == DELAYED


def test_never_succeeded_becomes_failed():
    assert status_of([], first_run_seconds_ago=10) == DELAYED
    assert status_of([], first_run_seconds_ago=40) == FAILED


def test_stale():
    assert is_stale(DELAYED) and is_stale(FAILED)
    assert not is_stale(OK) and not is_stale(RECOVERED)
