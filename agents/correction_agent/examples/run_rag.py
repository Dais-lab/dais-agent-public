#!/usr/bin/env python3
"""사후보정 RAG 사용 예시 — 이 파일 하나로 전체 흐름을 볼 수 있다.

    python -m agents.correction_agent.examples.run_rag            # 전체
    python -m agents.correction_agent.examples.run_rag --case 2   # 하나만
    python -m agents.correction_agent.examples.run_rag --http     # 컨테이너(:8003) 로

흐름
    [결함 분류기]  →  evidence_for()  →  프롬프트  →  [당신의 LLM]  →  validate()
      (다른 담당)      근거 조항·치수계산      조립         답변 생성        날조 검사

**최종 판정은 하지 않는다.** 연구원이 판단할 근거·조항·부족정보를 정리해 넘기는 것이 전부다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import urllib.request

AGENT_URL = os.getenv("CORRECTION_AGENT_URL", "http://localhost:8003")

# 분류기가 넘겨줄 법한 입력 4가지. 각각 다른 상황을 보여준다.
CASES = [
    {
        "_name": "① 정보 충분 — 치수 계산까지 나온다",
        "defect_label": "undercut",
        "inspection_method": "VT",
        "measurements": {"base_thickness_mm": 12.0, "defect_depth_mm": 0.3},
        "required_class": "1",
        "question": "이 결함이 허용되는가",
    },
    {
        "_name": "② 정보 부족 — 무엇이 더 필요한지 알려준다",
        "defect_label": "언더컷",  # 한글 라벨도 인식
        "inspection_method": "RT",
        "measurements": {},
    },
    {
        "_name": "③ 코퍼스 밖 — 지어내지 않고 멈춘다 (abstain)",
        "defect_label": "porosity",
        "question": "IQI 상질이 충족되었는가",
    },
    {
        "_name": "④ 모르는 라벨 — 사내 코드 15종에 없으면 거절",
        "defect_label": "banana",
    },
]


def _fmt(bundle: dict) -> str:
    out = []
    if bundle.get("defect"):
        d = bundle["defect"]
        out.append(
            f"  결함     : {d['our_code']} · {d['name_ko']} ({d['name_en']}) · {d['location']}"
        )
    if bundle.get("abstain"):
        out.append(f"  🛑 ABSTAIN : {bundle['abstain']['reason']}")
    for e in bundle.get("evidence") or []:
        body = e["text"].split("\n")[-1][:78]
        out.append(f"  근거     : [{e['via']:<9}] {e['citation_path']:<26} {body}")
    lc = bundle.get("limit_check")
    if lc and lc.get("computable"):
        verdict = "허용 범위 내" if lc["within_limit"] else "허용 범위 초과"
        out.append(f"  치수계산 : {lc['work']} → {verdict}")
    elif lc:
        out.append(f"  치수계산 : 불가 — {', '.join(lc['missing'])}")
    if bundle.get("missing_info"):
        out.append(f"  부족정보 : {', '.join(bundle['missing_info'])}")
    for g in bundle.get("coverage_gap") or []:
        out.append(f"  공백     : {g}")
    if bundle.get("applicability_note"):
        out.append("  적용한계 : " + textwrap.shorten(bundle["applicability_note"], 92))
    return "\n".join(out) or "  (내용 없음)"


def _via_http(case: dict) -> dict:
    body = json.dumps({k: v for k, v in case.items() if not k.startswith("_")}).encode()
    req = urllib.request.Request(
        f"{AGENT_URL}/rag/evidence", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=int, help="1~4 중 하나만 실행")
    ap.add_argument(
        "--http", action="store_true", help=f"라이브러리 대신 실행 중인 Agent({AGENT_URL}) 로 호출"
    )
    a = ap.parse_args()

    cases = [CASES[a.case - 1]] if a.case else CASES

    if a.http:
        print(f"모드: HTTP → {AGENT_URL}\n")
        run = _via_http
    else:
        print("모드: 라이브러리 (모델 적재에 10초쯤 걸린다)\n")
        from agents.correction_agent.rag import CorrectionRAG

        rag = CorrectionRAG()

        def run(case: dict) -> dict:
            b = rag.evidence_for(**{k: v for k, v in case.items() if not k.startswith("_")})
            return b.as_dict()

    last = None
    for case in cases:
        print("=" * 78)
        print(case["_name"])
        print("-" * 78)
        bundle = run(case)
        print(_fmt(bundle))
        print()
        last = bundle

    # ── 마지막 케이스로 가드레일 시연 ────────────────────────────────────
    print("=" * 78)
    print("가드레일 — 호출자 LLM 이 없는 조항을 지어내면 걸러진다")
    print("-" * 78)
    fake = {
        "judgement": "likely_acceptable",
        "evidence": [{"citation_path": "ISO 5817 Table 1"}],
    }  # 우리 코퍼스에 없는 조항
    if a.http:
        body = json.dumps({"answer": fake, "evidence": last.get("evidence") or []}).encode()
        req = urllib.request.Request(
            f"{AGENT_URL}/rag/validate", data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as f:
            res = json.load(f)
    else:
        from agents.correction_agent.rag import Bundle

        res = rag.validate(fake, Bundle(evidence=last.get("evidence") or []))
    print(f"  답변이 인용한 조항 : {[e['citation_path'] for e in fake['evidence']]}")
    print(f"  통과 여부         : {'통과' if res['ok'] else '🛑 차단'}")
    print(f"  날조로 걸린 조항   : {res['fabricated']}")
    print()
    print("→ 답변을 저장·표시하기 전에 validate() 를 반드시 통과시킬 것.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
