"""사후보정 Agent 검색기 — F안(질문 의도별 라우팅) + 매핑 확장.

풀려는 문제는 두 가지다.
  ⑥ 짧고 어휘가 조밀한 `defect-types` 15청크가 결함 관련 질문의 상위를 독점한다.
     → 질문 의도가 '절차·조치' 면 그 문서를 아예 후보에서 뺀다.
  다중 홉 → 결함코드가 정해지면 정의·육안·RT·규정 조항을 벡터 검색 없이 직접 인출한다.

팀 공통 인터페이스는 `search(query, top_k) -> list[Chunk]` 로 고정한다 (역할분배 문서 §0).
임베딩은 주입한다 — 환경마다 sentence-transformers 가용 여부가 달라서다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from agents.correction_agent.rag import config

DEFAULT_DB = str(config.VECTORDB_PATH)
COLLECTION = config.COLLECTION
DEFECT_DOC = "defect-types"
SLOTS = ("definition", "visual_acceptance", "rt_acceptance", "general", "requirement")

# 의도 판정 — 규칙 기반. 이 도메인은 질문 형태가 좁아 LLM 분류를 쓸 이유가 없다.
# 순서가 중요하다. "불합격 용접부는 어떻게 수리하는가" 는 '불합격' 때문에 허용기준으로
# 잘못 분류돼 결함유형표가 상위를 독점했다. 행동을 묻는 말이 있으면 그쪽이 우선이다.
INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "procedure",
        (
            "조치",
            "수리",
            "보수",
            "제거",
            "절차",
            "어떻게 해",
            "어떻게 수리",
            "해야 하나",
            "검사 방법",
            "몇 %",
            "repair",
            "remove",
            "procedure",
            "inspect",
        ),
    ),
    (
        "acceptance",
        (
            "허용",
            "합격",
            "불합격",
            "판정",
            "한계",
            "얼마까지",
            "기준치",
            "acceptance",
            "allowable",
            "reject",
            "limit",
        ),
    ),
    (
        "definition",
        (
            "뭐야",
            "무엇",
            "무슨",
            "정의",
            "뜻",
            "의미",
            "차이",
            "종류",
            "구분",
            "what is",
            "definition",
            "difference",
        ),
    ),
]

# G2 — 코퍼스에 근거가 없는 개념. 검색하기 전에 질의에서 잡아내 abstain 한다.
# 유사도 임계값으로는 못 자른다: 무관 질의가 0.82 로 나와 정답 대역(0.78~0.86)과 겹친다.
ABSENT_CONCEPTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("상질(IQI) 판정 기준", ("iqi", "상질", "투과도계", "image quality indicator", "penetrameter")),
    ("ISO 5817 품질등급 B/C/D", ("품질등급", "품질 등급", "quality level")),
    ("ISO 17636 촬영기법 Class A/B", ("촬영기법", "촬영 기법", "class a", "기법 class")),
    ("국내 규정 (KS·KGS)", ("kgs", "ks b", "국내 규정", "국내 기준")),
    (
        "RT 촬영 조건",
        (
            "초점거리",
            "노출시간",
            "기하학적 불선명",
            "geometric unsharpness",
            "source-to-film",
            "디지털 검출기",
        ),
    ),
)


# 리랭커 신뢰도 하한. 최고점이 이 값 미만이면 재정렬을 **버리고** 원래 순위를 유지한다.
#
# 왜 필요한가 — 리랭커를 무조건 걸면 조항번호는 좋아지지만 현장표현이 무너진다.
# 골드셋 38건에서 정답 순위가 어떻게 변했는지 세어 보면 유형별로 정반대다.
#
#   유형        개선  악화        확신도 범위
#   조항번호      6    0          0.257 ~ 0.993
#   영문         1    2(1→2)     0.936 ~ 0.997
#   한국어        2    1          0.011 ~ 0.978  (갈림)
#   현장표현      1    6          0.002 ~ 0.035  ← 전부 0점대
#
# 임계값을 어디에 둘 것인가 — R@3 를 실제로 바꾼 변화만 확신도 순으로 늘어놓으면 경계가 보인다.
#
#   0.002 손실 / 0.003 손실 / 0.006 개선 / 0.013 손실 / 0.015 손실 / 0.172 손실
#   ────────────────────── 여기가 경계 ──────────────────────
#   0.939 개선 / 0.944 개선 / 0.978 개선 / 0.989 개선
#
# **손실은 전부 0.172 이하, 확실한 개선은 전부 0.939 이상**이고 그 사이는 비어 있다.
# 임계값 스윕에서도 θ=0.18~0.80 이 전부 같은 결과(전체 R@3 0.84)를 낸다 — 넓은 고원이다.
# 0.5 는 그 빈 구간의 한가운데라 양쪽 오류로부터 가장 멀다.
#
#   θ=0.00 (무조건) 0.74  ·  θ=0.05  0.82  ·  θ=0.18~0.80  0.84  ·  적용 안 함  0.74
#
# **모델을 한국어 파인튜닝본(dragonkue/bge-reranker-v2-m3-ko)으로 바꾼 뒤
#   다시 재니 고원이 좁아졌다.**
#   θ=0.00  0.82  ·  θ=0.05~0.20  0.84  ·  θ=0.50  0.82
# 한국어 모델은 확신도가 낮아도 순위를 제대로 매기는 구간이 있어, 게이트를 높이면 그걸 버린다.
# → 0.1 채택 (0.05~0.2 고원의 가운데).
#
# ⚠️ 낮은 점수는 "근거 없음" 이 아니라 "질의 표현이 문서 표현과 멀다" 는 뜻이다.
#    현장표현 질의는 정답이 분명히 있는데도 0.00 이 나온다. abstain 신호로 쓰면 안 된다.
#    한국어 모델은 **확신도 0.000 인 질의에서도 순위는 맞혔다** — 점수와 순위 품질은 별개다.
RERANK_MIN_SCORE = config.RERANK_MIN_SCORE

# 질의에 조항 번호가 보이는가 — sparse 가중을 올릴지 판단한다
_CLAUSE = re.compile(r"\d+\.\d+|GWR\s*\d+")


@dataclass
class Chunk:
    id: str
    text: str
    citation_path: str
    doc_id: str
    chunk_type: str
    score: float | None = None
    via: str = "vector"  # vector | mapping
    meta: dict = field(default_factory=dict)

    def __repr__(self) -> str:  # 로그에서 바로 읽히도록
        s = f"{self.score:.3f}" if self.score is not None else " map "
        return f"[{s}] {self.citation_path} ({self.doc_id}, {self.via})"


class Retriever:
    def __init__(
        self,
        db: str = DEFAULT_DB,
        collection: str = COLLECTION,
        encoder: Callable[[str], list[float]] | None = None,
        reranker: Callable[[str, list[str]], list[float]] | None = None,
        rerank_threshold: float = RERANK_MIN_SCORE,
        use_bm25: bool = True,
    ):
        import chromadb

        self.db = db
        self.col = chromadb.PersistentClient(path=db).get_collection(collection)
        self.encoder = encoder
        self.reranker = reranker
        self.rerank_threshold = rerank_threshold
        self._bm25 = None
        if use_bm25:
            from agents.correction_agent.rag.bm25 import BM25Index

            self._bm25 = BM25Index(db)
        maps = json.loads((config.DATA / "defect_mappings.json").read_text(encoding="utf-8"))
        self.defects = {d["our_code"]: d for d in maps["defects"]}
        # 긴 별칭부터 맞춰야 "언더컷" 이 "컷" 에 먼저 걸리지 않는다
        self.alias = sorted(
            ((a.lower(), d["our_code"]) for d in maps["defects"] for a in d.get("aliases", [])),
            key=lambda x: -len(x[0]),
        )

    # ---------- 질의 해석 ----------
    def intent_of(self, query: str) -> str:
        q = query.lower()
        for intent, kws in INTENT_RULES:
            if any(k in q for k in kws):
                return intent
        return "general"

    def absent_concept(self, query: str) -> str | None:
        """질의가 코퍼스에 없는 개념을 묻고 있으면 그 이름을 돌려준다 (G2).

        ⚠️ "품질등급 B" 를 그냥 검색하면 NASA 의 `Class B joint`(용접 이음 등급)가
        0.787 로 반환된다. 전혀 다른 개념인데 형식이 그럴듯해 걸러지지 않는다.
        """
        q = query.lower()
        for name, kws in ABSENT_CONCEPTS:
            if any(k in q for k in kws):
                return name
        return None

    def code_of(self, query: str) -> str | None:
        q = query.lower()
        for alias, code in self.alias:
            # 2글자 코드는 단어 경계를 요구한다. "SD" 가 "used" 에 걸리면 안 된다.
            if len(alias) <= 2:
                if re.search(rf"\b{re.escape(alias)}\b", q):
                    return code
            elif alias in q:
                return code
        return None

    # ---------- 조회 ----------
    # 목차 행은 어떤 질문에도 답이 되지 않는다. 짧고 제목어로만 이루어져 있어
    # 본문 조항보다 높은 점수를 받아 정답을 밀어낸다(리랭커 잡음 구간에서 특히).
    NO_TOC = {"chunk_type": {"$ne": "toc_entry"}}

    def _where(self, intent: str) -> dict:
        # 의도로 문서를 **지우지 않는다.** 목차만 뺀다.
        # 절차·조치 질문에서 결함유형표를 밀어내는 일은 아래 감점(_penalty)이 맡는다.
        return dict(self.NO_TOC)

    def _penalty(self, intent: str) -> float | None:
        """절차·허용기준 질문에서 결함유형표에 매길 감점. 없으면 None.

        하드 필터(where 로 제외)와 감점은 **성능이 완전히 같았다** — 골드셋 38건에서
        R@1·R@3·MRR 이 소수점까지 일치한다. 그런데 실패 양상이 다르다.

            하드 필터 : 의도를 틀리면 그 문서가 후보에서 **사라진다**  → 정답을 못 찾음
            감점      : 의도를 틀려도 순위만 뒤로 밀린다              → 회복 가능

        의도 판정은 키워드 규칙이라 틀릴 수 있다(실제로 "불합격 용접부는 어떻게 수리하는가" 를
        허용기준으로 오분류한 적이 있다). 같은 값이면 **틀렸을 때 덜 아픈 쪽**을 고른다.
        """
        return config.DEFECT_DOC_PENALTY if intent in ("acceptance", "procedure") else None

    def _to_chunks(self, res: dict, via: str = "vector") -> list[Chunk]:
        out = []
        for i, cid in enumerate(res["ids"][0]):
            md = res["metadatas"][0][i]
            out.append(
                Chunk(
                    id=cid,
                    text=res["documents"][0][i],
                    citation_path=md["citation_path"],
                    doc_id=md["doc_id"],
                    chunk_type=md["chunk_type"],
                    score=1 - res["distances"][0][i],
                    via=via,
                    meta=md,
                )
            )
        return out

    def expand(self, code: str, slots: Iterable[str] = SLOTS) -> list[Chunk]:
        """결함코드에 매핑된 조항을 벡터 검색 없이 직접 인출한다 (다중 홉 1회 조회)."""
        d = self.defects.get(code)
        if not d:
            return []
        cites = [
            c
            for doc in ("milstd-2035a", "49cfr192", "nasa-std-5006a")
            for slot in slots
            for c in d.get(doc, {}).get(slot, [])
        ]
        if not cites:
            return []
        g = self.col.get(where={"citation_path": {"$in": cites}})
        return [
            Chunk(
                id=i,
                text=t,
                citation_path=m["citation_path"],
                doc_id=m["doc_id"],
                chunk_type=m["chunk_type"],
                score=None,
                via="mapping",
                meta=m,
            )
            for i, t, m in zip(g["ids"], g["documents"], g["metadatas"], strict=False)
        ]

    def search(
        self,
        query: str,
        top_k: int = 5,
        query_vec: list[float] | None = None,
        expand_mapping: bool = True,
    ) -> list[Chunk]:
        if query_vec is None:
            if self.encoder is None:
                raise RuntimeError("encoder 도 query_vec 도 없다. 둘 중 하나는 있어야 한다.")
            query_vec = self.encoder(query)

        absent = self.absent_concept(query)
        if absent:
            return []  # 근거 없음. 호출부는 abstain 리포트를 낸다.

        intent = self.intent_of(query)
        code = self.code_of(query)
        pool = max(top_k, 20) if self._bm25 else top_k
        res = self.col.query(
            query_embeddings=[query_vec], n_results=pool, where=self._where(intent)
        )
        hits = self._to_chunks(res)

        if self._bm25:
            # 조항 번호가 보이면 sparse 쪽 가중을 올린다. 균등 RRF 는 Dense 보다 나빴다
            # (전체 R@3 0.55 < 0.58). 실측으로 정한 값이 3.0 / 0.5 다.
            w = (
                config.SPARSE_WEIGHT_CLAUSE
                if _CLAUSE.search(query)
                else config.SPARSE_WEIGHT_DEFAULT
            )
            sparse = [d.id for d, _ in self._bm25.search(query, pool)]
            by_id = {h.id: h for h in hits}
            fused: dict[str, float] = {}
            for ranking, weight in (([h.id for h in hits], 1.0), (sparse, w)):
                for rank, cid in enumerate(ranking, start=1):
                    fused[cid] = fused.get(cid, 0.0) + weight / (60 + rank)

            penalty = self._penalty(intent)
            if penalty is not None:
                sparse_doc = {d.id: d.doc_id for d, _ in self._bm25.search(query, pool)}
                for cid in fused:
                    dd = by_id[cid].doc_id if cid in by_id else sparse_doc.get(cid)
                    if dd == DEFECT_DOC:
                        fused[cid] *= penalty
            order = [c for c, _ in sorted(fused.items(), key=lambda x: -x[1])][:pool]
            missing = [c for c in order if c not in by_id]
            if missing:
                g = self.col.get(ids=missing, include=["documents", "metadatas"])
                for i, d, m in zip(g["ids"], g["documents"], g["metadatas"], strict=False):
                    by_id[i] = Chunk(
                        id=i,
                        text=d,
                        citation_path=m["citation_path"],
                        doc_id=m["doc_id"],
                        chunk_type=m["chunk_type"],
                        score=None,
                        via="bm25",
                        meta=m,
                    )
            hits = [by_id[c] for c in order if c in by_id]

        if self.reranker and hits:
            scores = self.reranker(query, [h.text for h in hits])
            if scores and max(scores) >= self.rerank_threshold:
                for h, sc in zip(hits, scores, strict=False):
                    h.score, h.via = float(sc), "rerank"
                hits.sort(key=lambda h: -h.score)

        if expand_mapping and code and intent == "acceptance":
            # 허용기준 질문은 매핑 조항을 앞에 세운다. 벡터 순위보다 정확하다.
            slots = ("rt_acceptance", "visual_acceptance")
            seen = {h.citation_path for h in hits}
            mapped = [c for c in self.expand(code, slots) if c.citation_path not in seen]
            hits = mapped + hits
        return hits[: max(top_k, len(hits) if code else top_k)]

    def explain(self, query: str) -> dict:
        """왜 이렇게 검색했는지 — 리포트 provenance 와 디버깅용."""
        return {
            "intent": self.intent_of(query),
            "defect_code": self.code_of(query),
            "absent_concept": self.absent_concept(query),
        }

    def rt_evidence_available(self, code: str) -> bool:
        """RT 판정 근거가 있는가. abstain(G2)을 LLM 판단이 아니라 코드로 결정하기 위한 것."""
        d = self.defects.get(code)
        return bool(d and d["milstd-2035a"]["rt_acceptance"])
