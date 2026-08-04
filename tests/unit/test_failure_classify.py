"""실패 유형 분류 — 예외 타입만 근거로 삼는지 확인한다.

에러 메시지 문자열은 OS·로케일에 따라 달라지므로 판별 근거가 될 수 없다.
여기서는 메시지를 일부러 엉뚱하게 넣고도 타입만으로 갈리는지 본다.
"""
from __future__ import annotations

import socket
import urllib.error

from agents.common.tools.infra import classify_failure


def test_http_error_는_상태코드를_그대로_쓴다():
    exc = urllib.error.HTTPError("http://x", 503, "Service Unavailable", {}, None)
    assert classify_failure(exc) == "http_503"


def test_연결_거부():
    assert classify_failure(ConnectionRefusedError()) == "refused"


def test_이름_해석_실패():
    assert classify_failure(socket.gaierror()) == "dns"


def test_시간_초과():
    assert classify_failure(TimeoutError()) == "timeout"


def test_urlerror_에_감싸인_원인을_풀어낸다():
    """urlopen 은 실제 원인을 URLError.reason 에 감싸 전달한다."""
    assert classify_failure(urllib.error.URLError(ConnectionRefusedError())) == "refused"
    assert classify_failure(urllib.error.URLError(socket.gaierror())) == "dns"


def test_이중으로_감싸여도_풀어낸다():
    inner = urllib.error.URLError(TimeoutError())
    assert classify_failure(urllib.error.URLError(inner)) == "timeout"


def test_메시지가_그럴듯해도_타입이_아니면_unknown():
    """문자열을 근거로 삼지 않는다는 것을 고정한다."""
    assert classify_failure(RuntimeError("Connection refused by peer")) == "unknown"
    assert classify_failure(ValueError("timed out")) == "unknown"
