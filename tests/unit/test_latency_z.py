"""응답시간 편차(z) — 평소에 섞인 스파이크에 기준이 흔들리지 않는지 확인한다."""
from __future__ import annotations

from agents.common.tools.infra import _robust_z


def test_표본이_모자라면_판단하지_않는다():
    assert _robust_z([1.0] * 7, [99.0]) is None


def test_최근값이_없으면_판단하지_않는다():
    assert _robust_z([1.0] * 20, []) is None


def test_평소_수준이면_0_부근():
    base = [10.0, 11.0, 9.0, 10.5, 10.0, 9.5, 11.0, 10.0, 10.2, 9.8]
    z = _robust_z(base, [10.0])
    assert z is not None and abs(z) < 1.0


def test_크게_느려지면_큰_양수():
    base = [10.0, 11.0, 9.0, 10.5, 10.0, 9.5, 11.0, 10.0, 10.2, 9.8]
    z = _robust_z(base, [80.0])
    assert z is not None and z > 6


def test_평소에_섞인_스파이크가_기준을_흔들지_않는다():
    """평균·표준편차를 썼다면 이 스파이크가 기준을 키워 이상을 놓친다."""
    base = [10.0] * 15 + [500.0, 480.0]      # 평소에도 가끔 튀는 구간
    z = _robust_z(base, [60.0])
    assert z is not None and z > 3


def test_평소가_완전히_평탄해도_0으로_나누지_않는다():
    z = _robust_z([10.0] * 20, [10.0])
    assert z is not None and z == 0.0
