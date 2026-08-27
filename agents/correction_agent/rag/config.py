"""경로·모델·임계값을 한 곳에 모은다. 전부 환경변수로 덮어쓸 수 있다.

저장소 안에 호스트 경로를 하드코딩하지 않는다 (CLAUDE.md 절대 금지사항 2).
컨테이너에서는 compose 가 `VECTORDB_PATH` 를 넘긴다.
"""

from __future__ import annotations

import os
import pathlib

PKG = pathlib.Path(__file__).resolve().parent.parent  # agents/correction_agent
DATA = PKG / "data"

# ── VectorDB ────────────────────────────────────────────────────────────────
# chroma.sqlite3 + UUID 폴더 + doc_metadata.json 은 **한 세트**다.
# 폴더째 옮기고 하위 UUID 폴더명은 절대 바꾸지 않는다 (sqlite 가 그 이름으로 벡터를 찾는다).
# 60MB 바이너리라 git 에 올리지 않는다 → scripts/build_vectordb.py 로 만든다.
VECTORDB_PATH = pathlib.Path(os.getenv("VECTORDB_PATH", str(PKG / "vectordb")))
COLLECTION = os.getenv("VECTORDB_COLLECTION", "standards")

# ── 모델 ────────────────────────────────────────────────────────────────────
# e5 계열은 접두어가 필수다. 질의 "query: " / 문서 "passage: ".
# 한쪽만 붙이면 에러 없이 검색 품질만 조용히 떨어진다.
EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
QUERY_PREFIX = "query: "
DOC_PREFIX = "passage: "

# 한국어 파인튜닝본. 원본 BAAI/bge-reranker-v2-m3 대비 골드셋 38건에서
# 청크적중@1 0.63 → 0.68, MRR 0.73 → 0.76. 특히 현장 표현이 0.38 → 0.75.
RERANKER_MODEL = os.getenv("RAG_RERANKER_MODEL", "dragonkue/bge-reranker-v2-m3-ko")

# GPU 를 쓰지 않는다. 임베딩은 CPU 로 질의당 0.1초 남짓이면 충분하고,
# GPU 는 LLM 서빙(dais-llm)이 쓰고 있다.
DEVICE = os.getenv("RAG_DEVICE", "cpu")

# ── 검색 파라미터 (전부 골드셋 38건 실측으로 정한 값) ──────────────────────
TOP_K = int(os.getenv("RAG_TOP_K", "6"))
POOL_SIZE = int(os.getenv("RAG_POOL_SIZE", "20"))  # 리랭커에 넘길 후보 수

# 조항 번호가 보이면 sparse 가중을 올린다. 균등 RRF 는 벡터 단독보다 나빴다(0.55 < 0.58).
SPARSE_WEIGHT_CLAUSE = float(os.getenv("RAG_SPARSE_WEIGHT_CLAUSE", "3.0"))
SPARSE_WEIGHT_DEFAULT = float(os.getenv("RAG_SPARSE_WEIGHT_DEFAULT", "0.5"))

# 결함유형표는 짧고 어휘가 조밀해 절차·허용기준 질문에서 상위를 독점한다.
# 제외하지 않고 감점만 한다 — 의도 판정이 틀려도 순위만 밀리고 사라지지는 않는다.
DEFECT_DOC_PENALTY = float(os.getenv("RAG_DEFECT_DOC_PENALTY", "0.3"))

# 리랭커 신뢰도 하한. 최고점이 이 값 미만이면 재정렬을 버리고 1차 검색 순위를 쓴다.
RERANK_MIN_SCORE = float(os.getenv("RAG_RERANK_MIN_SCORE", "0.1"))
