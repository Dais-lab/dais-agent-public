"""사후보정 RAG — **인수인계 진입점**.

결함 분류(다른 담당)의 출력을 받아, LLM 프롬프트에 그대로 넣을 수 있는
**근거 번들**을 돌려준다. 호출자는 내부 구조(라우팅·RRF·매핑·리랭커)를 몰라도 된다.

    from correction_api import CorrectionRAG

    rag = CorrectionRAG()                       # 최초 1회 (모델 로딩 ~10초)
    bundle = rag.evidence_for(
        defect_label="undercut",                # 분류기가 준 결함 유형
        inspection_method="RT",
        measurements={"base_thickness_mm": 12.0, "defect_depth_mm": 0.3},
        required_class="1",
        question="이 결함이 허용되는가",          # 선택
    )
    # → bundle["evidence"] 를 프롬프트에 넣고, 답변을 rag.validate() 로 검증

필요 패키지: chromadb>=1.0 · sentence-transformers · rank_bm25
(모델 `intfloat/multilingual-e5-large` 최초 1회 다운로드 2.2GB)
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any

from agents.correction_agent.rag import config, limits
from agents.correction_agent.rag.retriever import Chunk, Retriever

DATA = config.DATA

# 인용 문서의 적용 한계. 이 문구가 빠지면 "형식은 완벽한데 우리 제품에 적용 안 되는" 답이 나온다.
DOMAIN_NOTE = {
    "milstd-2035a": "미 해군(NAVSEA) 조달 규격",
    "49cfr192": "미국 가스배관 연방안전규정",
    "nasa-std-5006a": "NASA 항공우주 용접 요구사항",
    "defect-types": "사내 결함 판정 코드표",
}
UNVERIFIED = ("milstd-2035a", "nasa-std-5006a")


@dataclass
class Bundle:
    """LLM 에 넘길 근거 묶음. dict 로 쓰려면 `.as_dict()`."""

    defect: dict | None = None
    evidence: list[dict] = field(default_factory=list)
    limit_check: dict | None = None
    missing_info: list[str] = field(default_factory=list)
    coverage_gap: list[str] = field(default_factory=list)
    applicability_note: str = ""
    status_note: str | None = None
    abstain: dict | None = None
    provenance: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    def prompt_block(self, max_chars: int = 700) -> str:
        """프롬프트에 바로 넣을 문자열. 인용주소가 앞에 오도록 되어 있다."""
        if self.abstain:
            return f"[근거 없음] {self.abstain['reason']}"
        parts = [
            f"[{i + 1}] citation_path: {e['citation_path']}\n"
            f"출처: {e['standard']} ({DOMAIN_NOTE.get(e['doc_id'], '')})\n"
            f"{e['text'][:max_chars]}"
            for i, e in enumerate(self.evidence)
        ]
        if self.limit_check and self.limit_check.get("computable"):
            parts.append(
                "[치수 계산 — 코드가 계산한 값이다. 다시 계산하지 말 것]\n"
                + self.limit_check["work"]
                + f"\n→ {'허용 범위 내' if self.limit_check['within_limit'] else '허용 범위 초과'}"
            )
        return "\n\n".join(parts)


class CorrectionRAG:
    def __init__(self, db: str | None = None, use_reranker: bool = True):
        from sentence_transformers import SentenceTransformer

        self.db = pathlib.Path(db or config.VECTORDB_PATH)
        if not (self.db / "chroma.sqlite3").exists():
            raise FileNotFoundError(
                f"VectorDB 가 없다: {self.db}\n"
                "  python -m agents.correction_agent.scripts.build_vectordb 로 만들거나,\n"
                "  VECTORDB_PATH 환경변수로 기존 DB 폴더를 가리켜라."
            )
        self._st = SentenceTransformer(config.EMBEDDING_MODEL, device=config.DEVICE)
        rr = self._make_reranker() if use_reranker else None
        self.rt = Retriever(db=str(self.db), encoder=self._encode, reranker=rr)
        self.maps = {
            d["our_code"]: d
            for d in json.loads((DATA / "defect_mappings.json").read_text(encoding="utf-8"))[
                "defects"
            ]
        }
        self.gaps = json.loads((DATA / "coverage_gaps.json").read_text(encoding="utf-8"))["gaps"]

    # ---------- 내부 ----------
    def _encode(self, q: str) -> list[float]:
        # e5 계열은 접두어가 필수다. 빠뜨리면 에러 없이 품질만 조용히 떨어진다.
        return self._st.encode([config.QUERY_PREFIX + q], normalize_embeddings=True)[0].tolist()

    def _make_reranker(self, model: str | None = None):
        from sentence_transformers import CrossEncoder

        ce = CrossEncoder(model or config.RERANKER_MODEL, max_length=512, device=config.DEVICE)
        return lambda q, texts: [float(s) for s in ce.predict([(q, t[:1800]) for t in texts])]

    # ---------- 공개 ----------
    def resolve(self, defect_label: str) -> str | None:
        """분류기가 준 라벨을 사내 결함코드로 정규화한다. 못 찾으면 None."""
        return self.rt.code_of(defect_label)

    def evidence_for(
        self,
        defect_label: str | None = None,
        *,
        inspection_method: str | None = None,
        measurements: dict | None = None,
        required_class: str | None = None,
        question: str | None = None,
        top_k: int | None = None,
    ) -> Bundle:
        top_k = top_k or config.TOP_K

        measurements = measurements or {}
        b = Bundle()

        # ① 코퍼스 밖 개념이면 검색하지 않고 즉시 abstain
        if question:
            absent = self.rt.absent_concept(question)
            if absent:
                b.abstain = {
                    "reason": f"'{absent}' 은 현재 코퍼스(문서 3종)에 근거가 없다",
                    "concept": absent,
                }
                b.coverage_gap = [b.abstain["reason"]]
                b.provenance = self._prov([])
                return b

        code = self.resolve(defect_label) if defect_label else None
        if defect_label and not code:
            b.abstain = {
                "reason": f"결함 라벨 '{defect_label}' 을 사내 코드 15종에 매핑할 수 없다",
                "known_codes": sorted(self.maps),
            }
            b.provenance = self._prov([])
            return b
        if code:
            d = self.maps[code]
            b.defect = {
                "our_code": code,
                "name_ko": d["name_ko"],
                "name_en": d["name_en"],
                "location": d["location"],
            }

        # ② 검색 — 결함·검사방법·질문에서 질의를 만든다
        queries: list[str] = []
        if code:
            ko = self.maps[code]["name_ko"]
            queries += [
                f"{ko}의 정의",
                f"{ko} 허용 한계가 얼마인가",
                f"{ko} 결함이 발견되면 어떻게 조치하는가",
            ]
        if inspection_method:
            queries.append(f"{inspection_method} 검사 요구사항")
        if question:
            queries.append(question)

        per_query = [self.rt.search(q, top_k=5) for q in queries]
        picked: dict[str, Any] = {}
        for res in per_query:  # 매핑 직접 인출 우선
            for h in res:
                if h.via in ("mapping", "limit_rule"):
                    picked.setdefault(h.citation_path, h)
        for rank in range(5):  # 나머지는 질의 간 라운드로빈
            for res in per_query:
                if rank < len(res):
                    picked.setdefault(res[rank].citation_path, res[rank])

        # ③ 치수 한계는 코드가 계산한다 (LLM 산술 금지)
        if code:
            lc = limits.check(code, required_class, measurements)
            if lc:
                b.limit_check = lc
                if not lc.get("computable"):
                    b.missing_info = sorted(set(b.missing_info + lc["missing"]))
                if lc["citation_path"] not in picked:
                    g = self.rt.col.get(
                        where={"citation_path": lc["citation_path"]},
                        include=["documents", "metadatas"],
                    )
                    for i, doc, m in zip(g["ids"], g["documents"], g["metadatas"], strict=False):
                        picked[lc["citation_path"]] = Chunk(
                            id=i,
                            text=doc,
                            citation_path=lc["citation_path"],
                            doc_id=m["doc_id"],
                            chunk_type=m["chunk_type"],
                            score=None,
                            via="limit_rule",
                            meta=m,
                        )
                        break

        hits = (
            [h for h in picked.values() if h.via in ("mapping", "limit_rule")]
            + [h for h in picked.values() if h.via not in ("mapping", "limit_rule")]
        )[:top_k]
        b.evidence = [
            {
                "citation_path": h.citation_path,
                "doc_id": h.doc_id,
                "standard": h.meta.get("doc_title", h.doc_id),
                "status": h.meta.get("status"),
                "source_url": h.meta.get("source_url"),
                "chunk_type": h.chunk_type,
                "text": h.text,
                "via": h.via,
            }
            for h in hits
        ]

        # ④ 공백 진단 — "없다" 가 아니라 "조항은 있는데 본문이 없다" 까지 말한다
        if (
            code
            and inspection_method == "RT"
            and not self.maps[code]["milstd-2035a"]["rt_acceptance"]
        ):
            note = f"{self.maps[code]['name_ko']}({code})의 RT 합격기준이 코퍼스에 없다"
            # "Under-Cut" ↔ "Undercut" 처럼 표기가 갈리므로 하이픈·공백을 지우고 맞춘다
            key = self.maps[code]["name_en"].replace("-", "").replace(" ", "").lower()
            rel = [
                g for g in self.gaps if key in g["title"].replace("-", "").replace(" ", "").lower()
            ]
            if rel:
                note += (
                    f" — {rel[0]['standard']} {rel[0]['section']} {rel[0]['title']}"
                    f"(p{rel[0]['page']}) 조항은 존재하나 본문 미확보"
                )
            b.coverage_gap.append(note)

        docs = {h.doc_id for h in hits}
        if docs:
            b.applicability_note = (
                "인용 문서는 "
                + " · ".join(sorted(DOMAIN_NOTE[d] for d in docs if d in DOMAIN_NOTE))
                + " 이다. 국내 발주처가 지정한 표준이 따로 있다면 그것이 우선하며, "
                "본 결과는 판정 근거가 아니라 검토 보조자료다."
            )
        if docs & set(UNVERIFIED):
            b.status_note = (
                "인용 문서 중 일부는 현행 유효 여부가 확인되지 않았다 "
                "(MIL-STD-2035A / NASA-STD-5006A)."
            )
        b.provenance = self._prov(hits)
        return b

    def _prov(self, hits) -> dict:
        return {
            "collection": "standards",
            "embedding": "multilingual-e5-large",
            "retriever": "dense+bm25(가중RRF)+의도라우팅+매핑확장",
            "reranker": "on" if self.rt.reranker else "off",
            "retrieved": [h.citation_path for h in hits],
        }

    # ---------- 호출자용 검증기 ----------
    def validate(self, answer: dict, bundle: Bundle) -> dict:
        """호출자 LLM 의 답변을 근거 번들과 대조한다 (가드레일 G1·G3·G4).

        이 도메인 최대 리스크는 **없는 조항을 지어내는 것**이고, 그건 문자열 대조로
        완전 자동 검출된다. 답변을 저장·표시하기 전에 반드시 통과시킬 것.
        """
        allowed = {e["citation_path"] for e in bundle.evidence}
        cited = [
            c.get("citation_path") if isinstance(c, dict) else c
            for c in (answer.get("evidence") or [])
        ]
        fake = [c for c in cited if c not in allowed]
        checks = [
            ("G1 조항 날조", not fake, f"근거 목록 밖 인용: {fake}" if fake else ""),
            (
                "G3 현행성 표시",
                not bundle.status_note or bool(answer.get("status_note") or bundle.status_note),
                "",
            ),
            (
                "G4 적용범위 경고",
                not bundle.applicability_note
                or bool(answer.get("applicability_note") or bundle.applicability_note),
                "",
            ),
        ]
        if bundle.abstain and cited:
            checks.append(("abstain 위반", False, "근거가 없는데 조항을 인용했다"))
        return {
            "ok": all(ok for _, ok, _ in checks),
            "checks": [{"rule": n, "pass": ok, "detail": d} for n, ok, d in checks],
            "fabricated": fake,
        }
