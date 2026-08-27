"""D안 — cross-encoder 재순위.

임베딩 환경과 chromadb 환경이 갈려 있어 3단계로 돈다.
  1) dump    (chromadb)            F안 top-N 후보를 본문째 덤프
  2) rerank  (sentence-transformers) cross-encoder 로 재채점
  3) score   (의존성 없음)          골드셋 대비 R@1/R@3/MRR

  python rerank.py dump   goldset.jsonl qvecs.json cand.json [--pool 20]
  python rerank.py rerank cand.json reranked.json
  python rerank.py score  goldset.jsonl reranked.json

리랭커는 질문과 문서를 **같이** 넣어 관련도를 매긴다(cross-encoder).
임베딩(bi-encoder)이 따로 벡터화해 거리만 재는 것과 달라 느리지만 정확하다.
그래서 1단계에서 넓게(20개) 뽑고 2단계에서 좁힌다.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

from agents.correction_agent.rag import config

DB = str(config.VECTORDB_PATH)
MODEL = "BAAI/bge-reranker-v2-m3"
CLAUSE = re.compile(r"\d+\.\d+|GWR\s*\d+")
TYPES = ("code", "eng", "kor", "field")


def _rows(path: str) -> list[dict]:
    return [
        json.loads(line)
        for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def dump(gold_path: str, vec_path: str, out: str, pool: int) -> None:
    sys.path.insert(0, DB)
    import chromadb  # noqa: E402

    from agents.correction_agent.rag.bm25 import BM25Index  # noqa: E402
    from agents.correction_agent.rag.retriever import Retriever  # noqa: E402

    rows = _rows(gold_path)
    vecs = json.loads(pathlib.Path(vec_path).read_text(encoding="utf-8"))["embeddings"]
    col = chromadb.PersistentClient(path=DB).get_collection("standards")
    ix = BM25Index(DB)
    rt = Retriever(db=DB)
    text_of = {}

    def fetch(ids: list[str]) -> None:
        missing = [i for i in ids if i not in text_of]
        if missing:
            g = col.get(ids=missing, include=["documents", "metadatas"])
            for i, d, m in zip(g["ids"], g["documents"], g["metadatas"], strict=False):
                text_of[i] = (d, m["citation_path"])

    out_rows = []
    for row, vec in zip(rows, vecs, strict=False):
        q = row["query"]
        w = 3.0 if CLAUSE.search(q) else 0.5
        intent = rt.intent_of(q)
        no_toc = {"chunk_type": {"$ne": "toc_entry"}}
        where = (
            {"$and": [no_toc, {"doc_id": {"$ne": "defect-types"}}]}
            if intent in ("acceptance", "procedure")
            else no_toc
        )
        dense = col.query(query_embeddings=[vec], n_results=pool, where=where)["ids"][0]
        skip_defect = intent in ("acceptance", "procedure")
        sparse = [
            d.id for d, _ in ix.search(q, pool) if not (skip_defect and d.doc_id == "defect-types")
        ]

        fused: dict[str, float] = {}
        for ranking, weight in ((dense, 1.0), (sparse, w)):
            for rank, cid in enumerate(ranking, start=1):
                fused[cid] = fused.get(cid, 0.0) + weight / (60 + rank)
        ids = [c for c, _ in sorted(fused.items(), key=lambda x: -x[1])][:pool]
        fetch(ids)
        out_rows.append(
            {
                "query": q,
                "type": row["type"],
                "gold": row["gold"],
                "candidates": [
                    {"id": i, "citation_path": text_of[i][1], "text": text_of[i][0]} for i in ids
                ],
            }
        )
    pathlib.Path(out).write_text(json.dumps(out_rows, ensure_ascii=False), encoding="utf-8")
    print(f"후보 덤프: {len(out_rows)}질의 × 최대 {pool}건 → {out}")


def rerank(cand_path: str, out: str, model: str = MODEL) -> None:
    from sentence_transformers import CrossEncoder

    rows = json.loads(pathlib.Path(cand_path).read_text(encoding="utf-8"))
    print(f"리랭커 모델: {model}")
    ce = CrossEncoder(model, max_length=512)
    for r in rows:
        pairs = [(r["query"], c["text"][:1800]) for c in r["candidates"]]
        if not pairs:
            continue
        for c, s in zip(r["candidates"], ce.predict(pairs, batch_size=16), strict=False):
            c["rerank_score"] = float(s)
        r["candidates"].sort(key=lambda c: -c["rerank_score"])
    pathlib.Path(out).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"재순위 완료: {len(rows)}질의 → {out}")


def score(gold_path: str, reranked: str) -> None:
    rows = json.loads(pathlib.Path(reranked).read_text(encoding="utf-8"))
    per = {t: [] for t in TYPES}
    for r in rows:
        ranked = [c["citation_path"] for c in r["candidates"][:10]]
        hit = next(
            (i for i, c in enumerate(ranked, 1) if any(c.startswith(g) for g in r["gold"])), None
        )
        per[r["type"]].append(
            (int(hit == 1), int(bool(hit) and hit <= 3), 1.0 / hit if hit else 0.0)
        )

    def agg(v):
        return (
            (
                f"{sum(x[0] for x in v) / len(v):.2f} {sum(x[1] for x in v) / len(v):.2f} "
                f"{sum(x[2] for x in v) / len(v):.2f}"
            )
            if v
            else "  —  "
        )

    allv = [x for t in TYPES for x in per[t]]
    print(f"{'안':<12}" + "".join(f"{t:^18}" for t in TYPES) + f"{'전체':^18}")
    print("-" * 102)
    print(f"{'D +Rerank':<12}" + "".join(f"{agg(per[t]):^18}" for t in TYPES) + f"{agg(allv):^18}")
    print("\n질의별 R@3")
    for r, t in zip(rows, [r["type"] for r in rows], strict=False):
        ranked = [c["citation_path"] for c in r["candidates"][:3]]
        ok = any(any(c.startswith(g) for g in r["gold"]) for c in ranked)
        print(f"  {'✅' if ok else '❌'}  [{t:<5}] {r['query']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["dump", "rerank", "score"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--pool", type=int, default=20)
    ap.add_argument("--model", default=MODEL)
    a = ap.parse_args()
    if a.mode == "dump":
        dump(a.args[0], a.args[1], a.args[2], a.pool)
    elif a.mode == "rerank":
        rerank(a.args[0], a.args[1], a.model)
    else:
        score(a.args[0], a.args[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
