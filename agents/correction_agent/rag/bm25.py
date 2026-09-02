"""BM25 희소 검색 + RRF 하이브리드.

설계상 주의 3가지 — 전부 실측에서 나온 제약이다.

 1. 색인 대상은 `document`(context) 가 아니라 **`embed_text`** 다.
    context 에는 문서명 헤더가 모든 청크에 반복돼 IDF 가 망가진다.
    `embed_text` 는 **메타데이터에 들어 있다** (`embed_text_backfill.py` 로 채운다).
    한때 외부 폴더(`chunks/*.jsonl`)에서 읽었는데 그 폴더가 옮겨지자 검색이 통째로 죽었다.
    **VectorDB 폴더는 그 자체로 한 세트여야 한다.**

 2. 조항 번호를 토큰으로 살린다. `192.243` `4.2.16` `1/64` 가 쪼개지면 BM25 를 쓰는 이유가 없다.
    또 CFR 은 조항 번호가 본문에 없고 `citation_path` 에만 있다.
    그래서 **인용주소를 본문 앞에 붙여** 색인한다.
    (실측: code 유형 R@3 0.40 → 0.70)

 3. MIL-STD 는 스캔 OCR 이라 i↔l 이 섞인다(`Ciass` `inciusion` `weid`).
    하드코딩 치환 대신 **i·l 을 한 글자로 접은 변형 토큰을 함께 색인**한다.
    질의에도 같은 변환을 건다.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

_TOKEN = re.compile(r"[A-Za-z]+|\d+(?:[./]\d+)*|[가-힣]+")


def _variants(tok: str) -> list[str]:
    out = [tok]
    if tok.isascii() and tok.isalpha():
        folded = tok.replace("l", "ı").replace("i", "ı")  # Ciass ↔ Class
        if folded != tok:
            out.append(folded)
    elif any(c.isdigit() for c in tok):
        fixed = tok.replace("i", "1").replace("l", "1").replace("O", "0")  # 4.2.i6 ↔ 4.2.16
        if fixed != tok:
            out.append(fixed)
    return out


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for tok in _TOKEN.findall(text.lower()):
        out.extend(_variants(tok))
        if len(tok) > 1 and "가" <= tok[0] <= "힣":
            out.extend(tok[i : i + 2] for i in range(len(tok) - 1))  # 한국어 bigram
    return out


@dataclass
class Doc:
    id: str
    citation_path: str
    doc_id: str


class BM25Index:
    def __init__(self, db: str | None = None):
        from agents.correction_agent.rag import config

        db = db or str(config.VECTORDB_PATH)
        from rank_bm25 import BM25Okapi

        # embedding_metadata.id 는 정수 rowid 다. Chroma 가 돌려주는 문자열 id 는
        # embeddings.embedding_id 이므로 반드시 조인해야 한다. 안 하면 dense 결과와
        # 대조가 전부 어긋나는데, 에러가 안 나서 "성능 0%" 로만 보인다.
        con = sqlite3.connect(f"file:{db}/chroma.sqlite3?mode=ro", uri=True)
        rows = list(
            con.execute("""
            select e.embedding_id,
             (select string_value from embedding_metadata where id=em.id and key='doc_id'),
             (select string_value from embedding_metadata where id=em.id and key='citation_path'),
             (select string_value from embedding_metadata where id=em.id and key='embed_text'),
             em.string_value
            from embedding_metadata em join embeddings e on e.id = em.id
            where em.key='chroma:document'
              and (select string_value from embedding_metadata
                   where id=em.id and key='chunk_type') != 'toc_entry'""")
        )

        self.docs: list[Doc] = []
        corpus: list[list[str]] = []
        self.miss = 0
        for cid, doc_id, cite, embed_text, ctx in rows:
            body = embed_text
            if not body:  # 백필 전 DB 라면 헤더 한 줄만 떼고 쓴다
                body = (ctx or "").split("\n", 1)[-1]
                self.miss += 1
            self.docs.append(Doc(cid, cite, doc_id))
            corpus.append(tokenize(f"{cite} {body}"))
        self.bm25 = BM25Okapi(corpus)

    def search(self, query: str, top_k: int = 20) -> list[tuple[Doc, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
        return [(self.docs[i], float(scores[i])) for i in order if scores[i] > 0]


def rrf(*rankings: list[str], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion — 점수 스케일이 다른 결과를 순위만으로 합친다."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, start=1):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda x: -x[1])
