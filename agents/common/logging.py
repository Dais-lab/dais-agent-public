"""Agent 컨테이너 공용 JSON 구조화 로깅.

각 로그는 ts/level/agent/name/msg 필드로 직렬화된다.
운영 단계에 Loki/ELK 수집을 붙일 때도 그대로 쓸 수 있다.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any


class _JSONFormatter(logging.Formatter):
    def __init__(self, agent_name: str) -> None:
        super().__init__()
        self.agent_name = agent_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "agent": self.agent_name,
            "name": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(agent_name: str, level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JSONFormatter(agent_name))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
