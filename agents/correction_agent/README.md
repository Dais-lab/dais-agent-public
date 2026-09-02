# Correction Agent — 사후보정 RAG

용접 결함 유형을 받아 **판정 근거가 될 조항을 찾아 넘긴다.**
pass/fail 을 결정하지 않는다. 연구원이 최종 판단할 **근거·조항·부족정보**를 정리하는 것이 역할이다.

```
[결함 분류]              [이 모듈]                    [호출자 LLM]      [연구원]
이미지 → 결함 유형  →  근거 조항 · 치수계산 · 부족정보  →  답변 생성  →  최종 판단
                       └ validate() 로 답변 검증 ←────┘
```

---

## 1. 빠른 시작

### 컨테이너

```bash
docker compose -f docker/docker-compose.yml up -d correction-agent
curl localhost:8003/rag/status
```

처음에는 `vectordb_ready: false` 다. **VectorDB 를 한 번 만들어야 한다.**

```bash
docker compose -f docker/docker-compose.yml exec correction-agent \
    python -m agents.correction_agent.scripts.build_vectordb
```

CPU 로 3,450 청크를 임베딩한다. 모델(2.2GB) 내려받기 + 임베딩으로 **10~20분**쯤 걸리고,
볼륨에 남으므로 **다시 할 필요 없다.**

### 예시 실행

```bash
# 컨테이너 안에서
docker compose -f docker/docker-compose.yml exec correction-agent \
    python -m agents.correction_agent.examples.run_rag

# 밖에서 HTTP 로
python -m agents.correction_agent.examples.run_rag --http
```

---

## 2. 호출 방법

### 라이브러리

```python
from agents.correction_agent.rag import CorrectionRAG

rag = CorrectionRAG()  # 최초 1회, 모델 적재 ~10초

bundle = rag.evidence_for(
    defect_label="undercut",  # "언더컷" / "UC" 도 인식
    inspection_method="RT",  # RT / VT / UT / MT / PT
    measurements={"base_thickness_mm": 12.0, "defect_depth_mm": 0.3},
    required_class="1",  # MIL-STD Class 1 / 2 / 3
    question="이 결함이 허용되는가",  # 선택
)

prompt = f"...{bundle.prompt_block()}..."  # 프롬프트에 그대로 삽입
answer = your_llm(prompt)

result = rag.validate(answer, bundle)  # ★ 저장·표시 전 필수
if not result["ok"]:
    ...  # result["fabricated"] 에 지어낸 조항
```

### HTTP

```bash
curl -X POST localhost:8003/rag/evidence -H 'Content-Type: application/json' -d '{
  "defect_label": "undercut",
  "inspection_method": "RT",
  "measurements": {"base_thickness_mm": 12.0, "defect_depth_mm": 0.3},
  "required_class": "1"
}'
```

| 엔드포인트 | 용도 |
| --- | --- |
| `GET /health` | 살아있는지 |
| `GET /rag/status` | VectorDB · 모델 적재 상태 |
| `POST /rag/evidence` | 결함 유형 → 근거 번들 |
| `POST /rag/validate` | 답변에 없는 조항이 인용됐는지 검사 |

---

## 3. 돌려주는 것

| 필드 | 내용 |
| --- | --- |
| `defect` | 라벨을 사내 코드로 정규화한 결과 (`UC` · 언더컷 · 표면) |
| `evidence[]` | 근거 조항 — `citation_path` · 출처 · 원문 · 현행성 |
| `limit_check` | **코드가 계산한** 치수 판정 |
| `missing_info[]` | 판정에 더 필요한 값. **한계식의 변수에서 자동 생성** |
| `coverage_gap[]` | 답할 수 없는 영역과 **그 이유** |
| `applicability_note` | 적용 한계 경고 |
| `abstain` | 근거가 없을 때. 이때 `evidence` 는 빈 배열 |

---

## 4. 호출자가 반드시 지킬 것 3가지

### ① `validate()` 를 통과시킨 뒤에만 저장·표시한다

이 도메인 최대 리스크는 **없는 조항을 지어내는 것**이고, 문자열 대조로 **완전 자동 검출**된다.

```python
rag.validate({"evidence": [{"citation_path": "ISO 5817 Table 1"}]}, bundle)
# → {"ok": False, "fabricated": ["ISO 5817 Table 1"]}
```

### ② `limit_check` 의 숫자를 LLM 이 다시 계산하게 하지 않는다

프롬프트에 *"치수 계산 결과는 이미 계산된 값이다. 다시 계산하지 말고 그대로 인용하라"* 를 넣을 것.

> **근거** — LLM 에게 *"1/64 inch 는 몇 mm 인가"* 를 물으면 **1.5875** 라고 답한다(정답 0.3969).
> 그 결과 허용(0.3 ≤ 0.397)인 케이스를 **불허**로 판정했다. 조항은 정확히 찾았고 형식도 완벽해서
> 눈으로는 안 걸러진다. 이 도메인의 한계값은 전부 인치 분수로 쓰여 있다.

### ③ `abstain` 이면 답을 만들지 않는다

근거가 0건이다. 이때 LLM 을 호출하면 반드시 지어낸다.
*"현재 문서로는 답할 수 없다"* 를 그대로 보여주고 `coverage_gap` 을 함께 노출한다.

---

## 5. 답할 수 있는 것 / 없는 것

| 질문 | 가능 | 근거 |
| --- | --- | --- |
| 이 결함은 무엇인가 | ✅ | 사내 결함유형표 15종 |
| 결함 코드(SD/CT/LF…)의 뜻 | ✅ | 〃 |
| 어떤 검사를 해야 하는가 | ✅ | 49 CFR 192.241 · 192.243 |
| 결함 발견 시 조치 | ✅ | 49 CFR 192.245 |
| 균열은 허용되는가 | ✅ | MIL-STD 4.2.4 · 49 CFR 192.245(a) |
| 언더컷 **육안** 허용 한계 | ✅ | MIL-STD 4.2.16 + 코드 계산 |
| 언더컷·슬래그·용락의 **RT** 허용 한계 | ❌ | 조항은 존재하나 **본문 미확보** (OCR 원본에 줄이 없다) |
| 기공·슬래그 RT 판정 수치 | ❌ | 판정 실체가 **그림**이라 텍스트로 못 읽는다 |
| 품질등급 B / 촬영기법 Class A·B / IQI 상질 | ❌ | 개념 자체가 코퍼스에 없음 → **자동 abstain** |
| 국내 규정(KS·KGS) 근거 | ❌ | 미적재 |

**인용 문서는 미 해군 조달 규격 · 미국 가스배관 규정 · NASA 항공우주 규격이다.**
발주처가 지정한 표준이 따로 있으면 그것이 우선한다. 모든 결과에 경고 문구가 들어간다.

---

## 6. 구성

```
agents/correction_agent/
├── api.py                  FastAPI 엔드포인트 (:8003)
├── rag/
│   ├── service.py          CorrectionRAG — 호출자는 이것만 알면 된다
│   ├── retriever.py        의도 라우팅 · 가중 RRF · 매핑 확장 · abstain
│   ├── bm25.py             희소 검색 · 토크나이저 · RRF
│   ├── limits.py           치수 한계 계산 (LLM 산술 대체)
│   └── config.py           경로·모델·임계값 (전부 환경변수로 덮어쓰기 가능)
├── data/
│   ├── chunks/*.jsonl      외부 문서 3종 청크 3,435건
│   ├── defect_types.md     사내 결함 유형표 15종 (원본 .csv 동봉)
│   ├── defect_mappings.json  결함 15종 ↔ 조항 69건 매핑
│   ├── coverage_gaps.json  목차엔 있으나 본문 없는 조항 29절
│   └── goldset.jsonl       검색 평가용 38건
├── scripts/
│   ├── build_vectordb.py   ★ 청크 → VectorDB (처음 한 번)
│   ├── eval_two_stage.py   문서 적중 / 청크 적중 2단계 평가
│   └── validate_mappings.py  인용주소 실재 검증
└── examples/run_rag.py     ★ 사용 예시
```

### 환경변수

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `VECTORDB_PATH` | `agents/correction_agent/vectordb` | DB 폴더. **rw 필요** |
| `RAG_DEVICE` | `cpu` | GPU 는 dais-llm 이 쓴다 |
| `RAG_EMBEDDING_MODEL` | `intfloat/multilingual-e5-large` | 바꾸면 **전체 재임베딩** |
| `RAG_RERANKER_MODEL` | `dragonkue/bge-reranker-v2-m3-ko` | 한국어 파인튜닝본 |
| `RAG_RERANK_MIN_SCORE` | `0.1` | 리랭커 신뢰도 하한 |
| `HF_HOME` | `/opt/dais/hf-cache` | 모델 캐시. 볼륨으로 빼야 재다운로드를 막는다 |

> ⚠️ **VectorDB 폴더는 한 세트다.** `chroma.sqlite3` + UUID 폴더 + `doc_metadata.json`.
> 폴더째 옮기고 **하위 UUID 폴더명은 절대 바꾸지 않는다** — sqlite 가 그 이름으로 벡터를 찾는다.
> **읽기 전용으로 마운트하면 안 된다** — Chroma 는 조회만 해도 sqlite 에 쓰기를 시도한다.

---

## 7. 검색 성능 (골드셋 38건)

평가를 **2단계**로 나눈다. 실패 원인이 라우팅인지 청킹인지 갈라야 고칠 수 있다.

| 안 | 문서 적중@3 | 청크 적중@3 | 청크 적중@1 | MRR |
| --- | --- | --- | --- | --- |
| 벡터 검색만 (출발점) | 0.92 | 0.58 | 0.42 | 0.52 |
| + BM25 가중 하이브리드 | 0.89 | 0.68 | 0.47 | 0.60 |
| + 의도 라우팅 | **0.97** | 0.74 | 0.50 | 0.63 |
| **+ 리랭커 (현재)** | **0.97** | **0.84** | **0.68** | **0.76** |

**문서 찾기는 사실상 끝났고(0.97), 남은 실패는 전부 문서 안에서 청크를 못 고르는 것이다.**

```bash
python -m agents.correction_agent.scripts.eval_two_stage \
    agents/correction_agent/data/goldset.jsonl <질의벡터.json>
```
