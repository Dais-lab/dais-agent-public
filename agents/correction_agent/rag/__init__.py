"""사후보정 RAG — 근거 조항 검색과 전달.

호출자는 `CorrectionRAG` 만 알면 된다.

    from agents.correction_agent.rag import CorrectionRAG

    rag = CorrectionRAG()
    bundle = rag.evidence_for(defect_label="undercut", inspection_method="RT")
    prompt = bundle.prompt_block()
    result = rag.validate(answer, bundle)
"""

from agents.correction_agent.rag.service import Bundle, CorrectionRAG

__all__ = ["Bundle", "CorrectionRAG"]
