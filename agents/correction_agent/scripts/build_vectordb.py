"""문서 청크 → Chroma VectorDB 구축. **처음 한 번만 돌리면 된다.**

VectorDB 는 60MB 바이너리라 git 에 올리지 않는다. 대신 원본 청크(`data/chunks/*.jsonl`)와
사내 결함 유형표(`data/defect_types.md`)를 커밋해 두고, 여기서 재생성한다.

    python -m agents.correction_agent.scripts.build_vectordb

CPU 로 3,450 청크를 임베딩한다. 최초 실행 때 모델(약 2.2GB)을 내려받고,
전체 10~20분쯤 걸린다. 이미 만들어진 DB 폴더가 있으면 `VECTORDB_PATH` 로 가리켜도 된다.

만들어지는 것
    chroma.sqlite3          본문 · 메타데이터 · 전문검색 인덱스
    <UUID>/                 벡터 본체 + 이웃 그래프(HNSW)
    → 이 둘은 **한 세트**다. 폴더째 옮기고 UUID 폴더명은 절대 바꾸지 않는다.
"""

from __future__ import annotations

import argparse
import json
import pathlib

from agents.correction_agent.rag import config

BATCH = 256
# 목차 행은 어떤 질문에도 답이 되지 않는다. 짧고 제목어로만 이루어져 본문 조항보다
# 높은 점수를 받아 정답을 밀어낸다. 지우지 않고 표시만 해 둔다 —
# 이 줄들이 "조항은 있는데 본문이 없다"를 말할 수 있는 유일한 근거다(coverage_gaps).
TOC_MARK = "Page:"


def _load_chunks(src: pathlib.Path) -> list[dict]:
    out = []
    for f in sorted(src.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def _defect_chunks() -> list[dict]:
    """사내 결함 유형표 markdown → 결함 1종 = 청크 1개."""
    from agents.correction_agent.scripts.load_defect_types import build, parse

    md = config.DATA / "defect_types.md"
    return [build(r) for r in parse(md)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(config.VECTORDB_PATH))
    ap.add_argument("--chunks", default=str(config.DATA / "chunks"))
    ap.add_argument("--force", action="store_true", help="이미 있어도 다시 만든다")
    a = ap.parse_args()

    out = pathlib.Path(a.out)
    if (out / "chroma.sqlite3").exists() and not a.force:
        print(f"이미 존재한다: {out}  (다시 만들려면 --force)")
        return 0

    import chromadb
    from sentence_transformers import SentenceTransformer

    rows = _load_chunks(pathlib.Path(a.chunks))
    print(f"외부 문서 청크 {len(rows)}건")

    ids, docs, metas, embed_src = [], [], [], []
    seq: dict[str, int] = {}
    for r in rows:
        m = dict(r["metadata"])
        doc_id = m["doc_id"]
        n = seq.get(doc_id, 0)
        seq[doc_id] = n + 1
        # 목차 행 표시 — 검색에서는 제외하되 컬렉션에는 남긴다
        if m.get("chunk_type") == "table_row" and TOC_MARK in r["context"]:
            m["chunk_type"] = "toc_entry"
            m["is_toc"] = "true"
        m["embed_text"] = r["embed_text"]  # BM25 색인용. 외부 파일 의존을 없앤다
        ids.append(f"{doc_id}::{n:05d}")
        docs.append(r["context"])
        metas.append({k: v for k, v in m.items() if v not in (None, "")})
        embed_src.append(r["embed_text"])

    for c in _defect_chunks():
        m = dict(c["metadata"])
        m["embed_text"] = c["embed_text"]
        ids.append(f"defect-types::{len(ids):05d}")
        docs.append(c["context"])
        metas.append(m)
        embed_src.append(c["embed_text"])
    print(f"사내 결함 유형표 포함 총 {len(ids)}청크")

    out.mkdir(parents=True, exist_ok=True)
    model = SentenceTransformer(config.EMBEDDING_MODEL, device=config.DEVICE)
    print(f"임베딩 시작 — {config.EMBEDDING_MODEL} on {config.DEVICE}")
    vecs = model.encode(
        [config.DOC_PREFIX + t for t in embed_src],
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=True,
    ).tolist()

    client = chromadb.PersistentClient(path=str(out))
    col = client.get_or_create_collection(config.COLLECTION, metadata={"hnsw:space": "cosine"})
    for s in range(0, len(ids), BATCH):
        e = s + BATCH
        col.upsert(ids=ids[s:e], embeddings=vecs[s:e], documents=docs[s:e], metadatas=metas[s:e])
    print(f"적재 완료: {col.count()}청크 → {out}")

    src_meta = config.DATA / "doc_metadata.json"
    if src_meta.exists():
        (out / "doc_metadata.json").write_text(
            src_meta.read_text(encoding="utf-8"), encoding="utf-8"
        )
        print("doc_metadata.json 복사")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
