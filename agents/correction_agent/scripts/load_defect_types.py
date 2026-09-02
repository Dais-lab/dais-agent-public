"""사내 결함 유형표(`data/defect_types.md`)를 파싱해 청크로 만든다.

`parse()` / `build()` 는 `scripts/build_vectordb.py` 가 그대로 재사용한다.
이 파일을 직접 실행하면 **이미 만들어진** 컬렉션에 결함 유형 15종만 덧붙인다.

결함 1종 = 청크 1개 (총 15). 기존 3문서와 같은 스키마를 따른다
  embed_text  검색용 (임베딩 대상)
  context     LLM 제공용 (document 필드에 저장)
  metadata    필터 · 출처용

환경이 갈려 있어 2단계로 나눠 쓸 수 있다.
  1) 임베딩 (sentence-transformers 필요)  --emit-embeddings vecs.json
  2) 적재   (chromadb 필요)               --from-embeddings vecs.json

사용:
  python load_defect_types.py --dry-run                     # 파싱만 (의존성 불필요)
  python load_defect_types.py --emit-embeddings vecs.json   # 임베딩만
  python load_defect_types.py --from-embeddings vecs.json   # 적재만
  python load_defect_types.py                               # 한 번에 (둘 다 있는 환경)
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

from agents.correction_agent.rag import config

_DEFAULT_MD = config.DATA / "defect_types.md"

DOC_ID = "defect-types"
COLLECTION = "standards"
DOC_TITLE = "용접 결함 유형 코드 정의 (사내 판정 코드표)"
AUTHORITY = "사내"
STATUS = "internal"
SOURCE_URL = "vectordb/결함 유형.csv"
DOC_PREFIX = "passage: "
STATUS_NOTE = (
    "사내 결함 판정 코드표(강관 원주 용접 / RT 판독). 2026-08-19 CSV 수신본을 옮긴 것. "
    "결함의 정의·위치·형상만 담고 있으며 허용 한계(치수·등급)는 없다 "
    "— 합격/불합격 판정 근거로 인용 불가. "
    "원본 CSV의 '비고4'(다른 코드로 판정되는 경우) 는 요청에 따라 제외했다. "
    "작성 주체·개정 이력은 확인되지 않음."
)

FIELDS = {
    "코드": "code",
    "영문명": "name_en",
    "한글명": "name_ko",
    "위치": "location",
    "정의": "definition",
    "형상 특징": "shape",
    "검색 동의어": "synonyms",
}


def parse(md_path: pathlib.Path) -> list[dict]:
    text = md_path.read_text(encoding="utf-8")
    # "## SD — Surface Defect (표면 결함)" 형태의 절만 취한다.
    pattern = re.compile(r"^## ([A-Z]{2}) — (.+?) \((.+?)\)\s*$", re.M)
    marks = list(pattern.finditer(text))
    out = []
    for i, m in enumerate(marks):
        body = text[m.end() : marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        rec = {"code": m.group(1), "name_en": m.group(2).strip(), "name_ko": m.group(3).strip()}
        for line in body.splitlines():
            hit = re.match(r"^- (.+?): (.*)$", line.strip())
            if hit and hit.group(1) in FIELDS:
                rec[FIELDS[hit.group(1)]] = hit.group(2).strip()
        out.append(rec)
    return out


def build(rec: dict) -> dict:
    code, en, ko = rec["code"], rec["name_en"], rec["name_ko"]
    definition = rec.get("definition", "")
    if definition.startswith("("):  # "(원본 CSV에 정의 없음)"
        definition = ""
    shape = rec.get("shape", "")
    loc = rec.get("location", "")
    syn = rec.get("synonyms", "")

    # 검색용 — 코드·한영 명칭·정의·형상·동의어를 한 줄로. 문장이 어색해도 된다.
    embed_text = " ".join(
        x
        for x in [
            f"{code} {en} {ko}",
            definition,
            f"{loc} 결함",
            shape,
            syn,
        ]
        if x
    ).strip()

    # 제공용 — 문서명·인용주소를 얹은 형태 (기존 3문서와 동일 규칙)
    citation = f"결함유형표 § {code}"
    lines = [f"{DOC_TITLE} — {citation}", f"{code} {en} ({ko}) · 위치: {loc}"]
    if definition:
        lines.append(f"정의: {definition}")
    if shape:
        lines.append(f"형상 특징: {shape}")
    context = "\n".join(lines)

    meta = {
        "doc_id": DOC_ID,
        "doc_title": DOC_TITLE,
        "authority": AUTHORITY,
        "status": STATUS,
        "source_url": SOURCE_URL,
        "element_type": "text",
        "chunk_type": "defect_definition",
        "citation_path": citation,
        "parent_id": f"{DOC_ID}#{loc}",
        "section": code,
        "section_title": f"{en} ({ko})",
        "is_appendix": "false",
        "code": code,
        "name_en": en,
        "name_ko": ko,
        "location": loc,
    }
    return {"embed_text": embed_text, "context": context, "metadata": meta}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=str(_DEFAULT_MD))
    ap.add_argument("--db", default=str(config.VECTORDB_PATH))
    ap.add_argument("--collection", default=COLLECTION)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--emit-embeddings")
    ap.add_argument("--from-embeddings")
    args = ap.parse_args()

    recs = parse(pathlib.Path(args.md))
    if len(recs) != 15:
        print(f"경고: 결함 {len(recs)}종 파싱됨 (15종 기대). md 형식을 확인할 것.", file=sys.stderr)
    chunks = [build(r) for r in recs]
    ids = [f"{DOC_ID}::{i:05d}" for i in range(len(chunks))]

    if args.dry_run:
        for cid, c in zip(ids, chunks, strict=False):
            print(
                f"--- {cid}  [{c['metadata']['citation_path']}] parent={c['metadata']['parent_id']}"
            )
            print("  embed :", c["embed_text"])
            print("  ctx   :", c["context"].replace("\n", " | "))
        print(f"\n총 {len(chunks)}청크. 실제 적재는 --dry-run 없이 실행.")
        return 0

    def encode():
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(config.EMBEDDING_MODEL, device=config.DEVICE)
        return model.encode(
            [DOC_PREFIX + c["embed_text"] for c in chunks], normalize_embeddings=True, batch_size=16
        ).tolist()

    if args.emit_embeddings:
        vecs = encode()
        pathlib.Path(args.emit_embeddings).write_text(
            json.dumps(
                {
                    "ids": ids,
                    "embeddings": vecs,
                    "documents": [c["context"] for c in chunks],
                    "metadatas": [c["metadata"] for c in chunks],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"임베딩 {len(vecs)}건 · {len(vecs[0])}차원 → {args.emit_embeddings}")
        return 0

    import chromadb

    if args.from_embeddings:
        cached = json.loads(pathlib.Path(args.from_embeddings).read_text(encoding="utf-8"))
        assert cached["ids"] == ids, "md 가 임베딩 생성 이후 바뀌었다. 다시 임베딩할 것."
        vecs = cached["embeddings"]
    else:
        vecs = encode()

    col = chromadb.PersistentClient(path=args.db).get_collection(args.collection)
    before = col.count()
    col.upsert(
        ids=ids,
        embeddings=vecs,
        documents=[c["context"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )
    print(f"적재 완료: {before} → {col.count()} 청크")

    meta_path = pathlib.Path(args.db) / "doc_metadata.json"
    notes = json.loads(meta_path.read_text(encoding="utf-8"))
    notes[DOC_ID] = {
        "doc_title": DOC_TITLE,
        "source_url": SOURCE_URL,
        "n_chunks": len(chunks),
        "status_note": STATUS_NOTE,
    }
    meta_path.write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"doc_metadata.json 갱신: {DOC_ID} 추가")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
