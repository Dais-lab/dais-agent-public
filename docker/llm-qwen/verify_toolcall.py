#!/usr/bin/env python3
"""LLM endpoint 검증 — 특히 tool-call 파서.

tool-call 파서 이름이 모델 출력 형식과 어긋나면 일반 응답은 정상으로 오는데
tool_calls 만 비어서 Agent 가 '조용히' 깨진다. 이 스크립트는 그 상태를 잡아낸다.

사용:
    ./deploy.sh verify                                  # 권장 (환경변수 자동 주입)
    python3 verify_toolcall.py
    LLM_URL=http://<GPU_SERVER_IP>:8000 python3 verify_toolcall.py

표준 라이브러리만 사용 — 추가 설치 불필요.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("LLM_URL", "http://127.0.0.1:8000").rstrip("/")
MODEL = os.getenv("LLM_MODEL", "")
API_KEY = os.getenv("LLM_API_KEY", "local")

TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "특정 도시의 현재 날씨를 조회한다",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "도시 이름"}},
            "required": ["city"],
        },
    },
}]


def _request(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {API_KEY}"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=180 if data else 30) as r:
        return json.load(r)


def main():
    print(f"대상: {BASE}\n")

    # ① 모델 목록 — alias 확인
    try:
        models = [m["id"] for m in _request("/v1/models")["data"]]
    except urllib.error.URLError as e:
        print(f"❌ 연결 실패: {e}")
        print("   서버가 로딩 중이거나(첫 기동 시 다운로드 포함) 포트/바인딩 설정을 확인하세요.")
        return 1
    print("① /v1/models")
    for m in models:
        print(f"     - {m}")

    model = MODEL if MODEL in models else (MODEL or models[0])
    if MODEL and MODEL not in models:
        print(f"\n   ⚠️ 요청한 모델명 '{MODEL}' 이 목록에 없습니다 — served-model-name 확인 필요")
    print(f"\n   사용할 모델: {model}\n")

    # ② 일반 응답 + reasoning 파서
    print("② 일반 응답 / reasoning 파서")
    try:
        r = _request("/v1/chat/completions", {
            "model": model,
            "messages": [{"role": "user", "content": "한 문장으로 자기소개해줘."}],
            "max_tokens": 128, "temperature": 0.7,
        })
        msg = r["choices"][0]["message"]
        content = (msg.get("content") or "").strip()
        print(f"     {content[:200]}")
        if not content:
            print("     ⚠️ content 가 비어 있음 — reasoning-parser 설정 확인")
        for marker in ("<|channel", "<think", "thought"):
            if marker in content:
                print(f"     ⚠️ 사고과정 토큰({marker}) 노출 — reasoning-parser 불일치")
                break
    except Exception as e:
        print(f"     ❌ 실패: {e}")
        return 1

    # ③ tool calling — 핵심
    print("\n③ tool calling (핵심 검증)")
    try:
        r = _request("/v1/chat/completions", {
            "model": model,
            "messages": [{"role": "user", "content": "서울 날씨 알려줘."}],
            "tools": TOOLS,
            "tool_choice": "auto",
            "max_tokens": 512, "temperature": 0,
        })
        msg = r["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        finish = r["choices"][0].get("finish_reason")

        if not calls:
            print(f"     ❌ tool_calls 비어 있음 (finish_reason={finish})")
            print(f"        content: {(msg.get('content') or '')[:300]}")
            print()
            print("     → --tool-call-parser 가 모델 출력 형식과 맞지 않습니다.")
            print("       .env 의 LLM_TOOL_PARSER 를 바꿔가며 재시도:")
            print("         qwen3_coder  (HF 모델 카드 권장)")
            print("         qwen3_xml    (vLLM recipes 권장)")
            print("         hermes       (Qwen 계열 범용 fallback)")
            print("       변경 후: ./deploy.sh recreate  (restart 로는 플래그가 안 바뀜)")
            return 1

        fn = calls[0]["function"]
        print(f"     ✅ tool_calls 수신 (finish_reason={finish})")
        print(f"        name      = {fn['name']}")
        print(f"        arguments = {fn['arguments']}")
        try:
            args = json.loads(fn["arguments"])
        except json.JSONDecodeError:
            print("        ❌ arguments 가 JSON 이 아님 — 파서 불일치")
            return 1
        if "city" in args:
            print("        ✅ 인자 파싱 정상 — 파서 설정이 올바릅니다.")
        else:
            print("        ⚠️ 'city' 인자 누락 — 프롬프트/스키마 확인 필요")
    except Exception as e:
        print(f"     ❌ 실패: {e}")
        return 1

    print("\n✅ 전체 통과 — Agent 연결 가능 상태입니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
