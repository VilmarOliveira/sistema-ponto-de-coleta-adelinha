from datetime import datetime, timedelta
from recovery_wait import recovery_wait_message


def test_short_wait_rounds_up():
    now = datetime(2026, 11, 15, 12)
    message = str(recovery_wait_message({'total': 1, 'latest': (now-timedelta(seconds=12.5)).isoformat()}, now))
    assert 'há pouco' in message
    assert 'data-recovery-wait="48"' in message


def test_window_limit_expires_from_oldest_not_latest_request():
    now = datetime(2026, 11, 15, 12)
    recent = {'total': 3, 'earliest': (now-timedelta(minutes=14)).isoformat(),
              'latest': (now-timedelta(seconds=20)).isoformat()}
    message = str(recovery_wait_message(recent, now))
    assert 'limite' in message
    assert 'data-recovery-wait="60"' in message


def test_short_limit_can_outlast_window_limit():
    now = datetime(2026, 11, 15, 12)
    recent = {'total': 3, 'earliest': (now-timedelta(minutes=14, seconds=59)).isoformat(),
              'latest': (now-timedelta(seconds=5)).isoformat()}
    assert 'data-recovery-wait="55"' in str(recovery_wait_message(recent, now))
