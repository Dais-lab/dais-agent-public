"""실패 유형 분류 — 예외 타입만 근거로 삼는지 확인한다.

에러 메시지 문자열은 OS·로케일에 따라 달라지므로 판별 근거가 될 수 없다.
여기서는 메시지를 일부러 그럴듯하게 넣고도 타입만으로 갈리는지 본다.
"""
from __future__ import annotations

import socket
import urllib.error

from agents.common.tools.infra import classify_failure


def test_http_error_uses_status_code() -> None:
    """HTTP 오류는 상태코드를 그대로 유형으로 쓴다."""
    exc = urllib.error.HTTPError("http://x", 503, "Service Unavailable", {}, None)
    assert classify_failure(exc) == "http_503"


def test_connection_refused() -> None:
    """포트에 리스닝 프로세스가 없는 경우."""
    assert classify_failure(ConnectionRefusedError()) == "refused"


def test_name_resolution_failure() -> None:
    """그런 이름의 호스트가 없는 경우."""
    assert classify_failure(socket.gaierror()) == "dns"


def test_timeout() -> None:
    """응답이 시간 안에 오지 않은 경우."""
    assert classify_failure(TimeoutError()) == "timeout"


def test_unwraps_urlerror_reason() -> None:
    """urlopen 은 실제 원인을 URLError.reason 에 감싸 전달한다."""
    assert classify_failure(urllib.error.URLError(ConnectionRefusedError())) == "refused"
    assert classify_failure(urllib.error.URLError(socket.gaierror())) == "dns"


def test_unwraps_nested_urlerror() -> None:
    """두 겹으로 감싸여도 끝까지 풀어낸다."""
    inner = urllib.error.URLError(TimeoutError())
    assert classify_failure(urllib.error.URLError(inner)) == "timeout"


def test_message_is_not_evidence() -> None:
    """메시지가 그럴듯해도 타입이 아니면 unknown 이다.

    문자열을 근거로 삼기 시작하면 로케일이 바뀐 서버에서 조용히 오분류된다.
    """
    assert classify_failure(RuntimeError("Connection refused by peer")) == "unknown"
    assert classify_failure(ValueError("timed out")) == "unknown"
