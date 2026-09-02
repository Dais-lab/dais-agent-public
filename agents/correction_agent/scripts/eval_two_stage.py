"""2단계 평가 — **문서를 제대로 찾았는가 / 그 안에서 청크를 제대로 골랐는가.**

R@3 하나로는 실패 원인이 안 보인다. 두 단계가 섞여 있고 고치는 방법이 다르다.

    질문 → [어느 문서인가]  → [그 문서 안 어느 청크인가] → 답
             라우팅·필터           청킹·리랭커

  python eval_two_stage.py goldset.jsonl qvecs.json [리랭커이름=reranked.json ...]
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

from agents.correction_agent.rag import config
from agents.correction_agent.rag.bm25 import BM25Index  # noqa: E402

DB = str(config.VECTORDB_PATH)
TYPES = ("code", "eng", "kor", "field")
CLAUSE = re.compile(r"\d+\.\d+|GWR\s*\d+")
NO_TOC = {"chunk_type": {"$ne": "toc_entry"}}
POOL = 20
GATE = 0.1
DOC_PREFIX = (
    ("49 CFR", "49cfr192"),
    ("milstd", "milstd-2035a"),
    ("p", "milstd-2035a"),
    ("NASA", "nasa-std-5006a"),
    ("결함유형표", "defect-types"),
)


def doc_of(c: str) -> str:
    for pre, d in DOC_PREFIX:
        if c.startswith(pre):
            return d
    return "?"


def two_stage(cites: list[str], gold: list[str]) -> tuple[int, int, int, float]:
    """문서적중@3, 청크적중@1, 청크적중@3, MRR"""
    gd = {doc_of(g) for g in gold}
    doc_hit = int(any(doc_of(c) in gd for c in cites[:3]))
    for i, c in enumerate(cites, 1):
        if any(c.startswith(g) for g in gold):
            return doc_hit, int(i == 1), int(i <= 3), 1 / i
    return doc_hit, 0, 0, 0.0


def main() -> int:
    gold_path, vec_path = sys.argv[1], sys.argv[2]
    extra = [a.split("=", 1) for a in sys.argv[3:]]

    rows = [
        json.loads(line)
        for line in pathlib.Path(gold_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    vecs = json.loads(pathlib.Path(vec_path).read_text(encoding="utf-8"))["embeddings"]

    import chromadb

    from agents.correction_agent.rag.retriever import Retriever

    col = chromadb.PersistentClient(path=DB).get_collection("standards")
    ix = BM25Index(DB)
    rt = Retriever(db=DB, use_bm25=False)
    cite_of = {d.id: d.citation_path for d in ix.docs}

    arms = ["A 벡터만", "B BM25만", "C 하이브리드(균등)", "C2 하이브리드(가중)", "F +라우팅"]
    reranked = {}
    for name, path in extra:
        reranked[f"{name}"] = {
            r["query"]: r for r in json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        }
        arms.append(name)

    res = {a: {t: [] for t in TYPES} for a in arms}
    f_order: dict[str, list[str]] = {}

    for row, vec in zip(rows, vecs, strict=False):
        q, t = row["query"], row["type"]
        w = 3.0 if CLAUSE.search(q) else 0.5
        dense = col.query(query_embeddings=[vec], n_results=POOL, where=NO_TOC)["ids"][0]
        sparse = [d.id for d, _ in ix.search(q, POOL)]

        def fuse(dn, sp, weight, penalty=None):
            s = {}
            for rk, wt in ((dn, 1.0), (sp, weight)):
                for r, cid in enumerate(rk, 1):
                    s[cid] = s.get(cid, 0.0) + wt / (60 + r)
            if penalty:
                for cid in s:
                    if cid in cite_of and doc_of(cite_of[cid]) == "defect-types":
                        s[cid] *= penalty
            return [c for c, _ in sorted(s.items(), key=lambda x: -x[1])]

        pen = 0.3 if rt.intent_of(q) in ("acceptance", "procedure") else None
        got = {
            "A 벡터만": dense,
            "B BM25만": sparse,
            "C 하이브리드(균등)": fuse(dense, sparse, 1.0),
            "C2 하이브리드(가중)": fuse(dense, sparse, w),
            "F +라우팅": fuse(dense, sparse, w, pen),
        }
        f_cites = [cite_of.get(i, "") for i in got["F +라우팅"][:POOL]]
        f_order[q] = f_cites
        for a in arms[:5]:
            res[a][t].append(two_stage([cite_of.get(i, "") for i in got[a][:10]], row["gold"]))
        for name, table in reranked.items():
            r = table[q]
            top = max(c["rerank_score"] for c in r["candidates"])
            cites = [c["citation_path"] for c in r["candidates"]] if top >= GATE else f_cites
            res[name][t].append(two_stage(cites[:10], row["gold"]))

    def agg(v, i):
        return sum(x[i] for x in v) / len(v)

    print(f"골드셋 {len(rows)}건 · 리랭커 게이트 θ={GATE}\n")
    print("■ 2단계 평가 — 문서를 찾았는가 / 청크를 골랐는가\n")
    print(
        f"{'안':<22}{'문서적중@3':>12}{'청크적중@3':>12}"
        f"{'청크적중@1':>12}{'MRR':>8}{'문서○ 청크✗':>14}"
    )
    print("-" * 82)
    for a in arms:
        allv = [x for t in TYPES for x in res[a][t]]
        gap = sum(1 for x in allv if x[0] and not x[2])
        print(
            f"{a:<22}{agg(allv, 0):>12.2f}{agg(allv, 2):>12.2f}{agg(allv, 1):>12.2f}"
            f"{agg(allv, 3):>8.2f}{gap:>12}건"
        )

    print("\n■ 질의 유형별 (문서적중@3 / 청크적중@3)\n")
    print(f"{'안':<22}" + "".join(f"{t:^16}" for t in TYPES))
    print("-" * 86)
    for a in arms:
        line = f"{a:<22}"
        for t in TYPES:
            v = res[a][t]
            line += f"{agg(v, 0):.2f} / {agg(v, 2):.2f}".center(16)
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
