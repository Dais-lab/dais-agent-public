"""응답시간 편차(z) — 평소에 섞인 스파이크에 기준이 흔들리지 않는지 확인한다."""
from __future__ import annotations

from agents.common.tools.infra import _robust_z


def test_returns_none_when_baseline_too_short() -> None:
    """표본이 모자라면 판단하지 않는다."""
    assert _robust_z([1.0] * 7, [99.0]) is None


def test_returns_none_without_recent_values() -> None:
    assert _robust_z([1.0] * 20, []) is None


def test_normal_level_scores_near_zero() -> None:
    base = [10.0, 11.0, 9.0, 10.5, 10.0, 9.5, 11.0, 10.0, 10.2, 9.8]
    z = _robust_z(base, [10.0])
    assert z is not None and abs(z) < 1.0


def test_large_slowdown_scores_high() -> None:
    base = [10.0, 11.0, 9.0, 10.5, 10.0, 9.5, 11.0, 10.0, 10.2, 9.8]
    z = _robust_z(base, [80.0])
    assert z is not None and z > 6


def test_baseline_spikes_do_not_mask_anomaly() -> None:
    """평균·표준편차를 썼다면 이 스파이크가 기준을 키워 이상을 놓친다.

    중앙값·IQR 을 쓰는 이유가 이 경우다.
    """
    base = [10.0] * 15 + [500.0, 480.0]
    z = _robust_z(base, [60.0])
    assert z is not None and z > 3


def test_flat_baseline_does_not_divide_by_zero() -> None:
    """평소가 완전히 평탄하면 최소 폭을 준다."""
    z = _robust_z([10.0] * 20, [10.0])
    assert z is not None and z == 0.0
