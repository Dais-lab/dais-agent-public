"""Correction Agent FastAPI 엔드포인트.

포트: 8003 (docs/PORTS.md 참고)

    GET  /health          살아있는지
    GET  /llm-check       외부 LLM endpoint 검증 (공용 factory)
    GET  /rag/status      VectorDB · 모델 적재 상태
    POST /rag/evidence    ★ 결함 유형 → 근거 조항 번들
    POST /rag/validate    호출자 LLM 답변을 근거 번들과 대조 (조항 날조 검출)

RAG 모델은 **첫 요청 때 적재**한다(lazy). 컨테이너 기동을 막지 않기 위해서다.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from agents.common import create_app

logger = logging.getLogger("correction_agent")

app = create_app("correction_agent")

_rag: Any = None
_rag_error: str | None = None
_lock = threading.Lock()


def get_rag():
    """CorrectionRAG 싱글턴. 모델 적재가 오래 걸려 첫 요청에서 한 번만 한다."""
    global _rag, _rag_error
    if _rag is not None:
        return _rag
    with _lock:
        if _rag is None and _rag_error is None:
            try:
                from agents.correction_agent.rag import CorrectionRAG

                logger.info("RAG 적재 시작 (임베딩·리랭커 모델)")
                _rag = CorrectionRAG()
                logger.info("RAG 준비 완료")
            except Exception as exc:  # noqa: BLE001
                _rag_error = str(exc)
                logger.exception("RAG 적재 실패")
    if _rag is None:
        raise HTTPException(status_code=503, detail=f"RAG 사용 불가: {_rag_error}")
    return _rag


class EvidenceRequest(BaseModel):
    defect_label: str | None = Field(
        None, description="분류기 출력. '언더컷' / 'undercut' / 'UC' 다 인식"
    )
    inspection_method: str | None = Field(None, description="RT / VT / UT / MT / PT")
    measurements: dict[str, float | None] = Field(default_factory=dict)
    required_class: str | None = Field(None, description="MIL-STD Class 1 / 2 / 3")
    question: str | None = Field(None, description="연구원 질문 원문")
    top_k: int | None = None


class ValidateRequest(BaseModel):
    answer: dict = Field(..., description="호출자 LLM 이 만든 답변 JSON")
    evidence: list[dict] = Field(..., description="evidence_for 가 돌려준 evidence 배열")


@app.get("/rag/status")
def rag_status() -> dict:
    from agents.correction_agent.rag import config

    db = config.VECTORDB_PATH
    ready = (db / "chroma.sqlite3").exists()
    return {
        "vectordb_path": str(db),
        "vectordb_ready": ready,
        "loaded": _rag is not None,
        "error": _rag_error,
        "embedding_model": config.EMBEDDING_MODEL,
        "reranker_model": config.RERANKER_MODEL,
        "device": config.DEVICE,
        "hint": None
        if ready
        else "python -m agents.correction_agent.scripts.build_vectordb 로 DB 를 만들어라",
    }


@app.post("/rag/evidence")
def rag_evidence(req: EvidenceRequest) -> dict:
    """결함 유형을 받아 근거 조항 번들을 돌려준다.

    `defect_label` 과 `question` 중 최소 하나는 있어야 한다.
    근거가 없으면 `abstain` 이 채워지고 `evidence` 는 빈 배열이다 — 이때 LLM 을 호출하면 안 된다.
    """
    if not req.defect_label and not req.question:
        raise HTTPException(status_code=422, detail="defect_label 과 question 중 하나는 필요하다")
    bundle = get_rag().evidence_for(
        defect_label=req.defect_label,
        inspection_method=req.inspection_method,
        measurements=req.measurements,
        required_class=req.required_class,
        question=req.question,
        top_k=req.top_k,
    )
    out = bundle.as_dict()
    out["prompt_block"] = bundle.prompt_block()
    return out


@app.post("/rag/validate")
def rag_validate(req: ValidateRequest) -> dict:
    """호출자 LLM 답변에 **없는 조항이 인용됐는지** 검사한다 (가드레일 G1).

    이 도메인 최대 리스크가 조항 날조이고, 문자열 대조로 완전 자동 검출된다.
    답변을 저장·표시하기 전에 반드시 통과시킬 것.
    """
    from agents.correction_agent.rag import Bundle

    return get_rag().validate(req.answer, Bundle(evidence=req.evidence))
