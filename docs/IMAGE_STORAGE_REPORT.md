# 이미지 DB 관리 전략 보고서

작성일: 2026-05-13

## 1. 결론

현재 DaiS-Agent는 PostgreSQL, MinIO, MLflow, Airflow, FastAPI 추론 API를 이미 사용하고 있다. 따라서 이미지 관리 전략은 다음 구조가 가장 적합하다.

- **PostgreSQL**: 케이스, 이미지, 추론 상태, 결함 결과, 페이지네이션용 메타데이터 저장
- **MinIO**: 원본 이미지, heatmap, annotation 등 큰 바이너리 파일 저장
- **MLflow**: 모델, 실험, 모델 산출물 관리 유지

즉, 이미지를 PostgreSQL `bytea`에 직접 넣기보다 **이미지 파일은 MinIO에 저장하고 DB에는 object key, checksum, 크기, MIME type, 상태, 추론 결과만 저장**하는 방식을 권장한다.

## 2. 현재 코드 기준 현황

현재 README와 문서 기준 시스템은 다음 상태다.

- `docker/docker-compose.yml`
  - PostgreSQL 컨테이너 1개 사용
  - DB는 `mlflow_db`, `airflow_db`로 분리
  - MinIO는 MLflow artifact storage로 사용
- `model/inference/api.py`
  - `POST /predict`가 `case_id`를 받아 `/opt/dais/data/inference/inbox/<case_id>` 폴더를 처리
- `model/inference/predict.py`
  - 입력 폴더에서 이미지 파일을 읽음
  - `data/output/<case_id>/<image_basename>/`에 `original.png`, `heatmap.png`, `annotation.png`, `result.json` 저장
  - `data/output/<case_id>/meta.json`에 케이스 요약 저장
- `docker/airflow/dags/inference_pipeline.py`
  - inbox 폴더 스캔
  - `ml-inference:8004/predict` 호출
  - 처리 후 archive 폴더로 이동

나중에 홈페이지에서 10장씩 이미지를 보여주고 결함탐지 결과를 조회해야 하므로, 폴더 스캔만으로는 상태 조회, 검색, 페이지네이션, 중복 방지, 결과 이력 관리가 불편해진다. 이 부분을 DB가 맡아야 한다.

## 3. 어떤 DB를 사용하면 좋은가

### 권장안: PostgreSQL + MinIO

PostgreSQL은 관계형 메타데이터에 적합하다.

- 케이스별 이미지 목록
- 업로드/검증/추론중/완료/실패 상태
- defect 여부, score, bbox JSON
- 모델 버전, MLflow run/model URI
- 10장 단위 페이지네이션
- 사용자 화면의 필터링/정렬

MinIO는 이미지 같은 큰 BLOB 저장에 적합하다.

- 원본 이미지
- heatmap 이미지
- annotation 이미지
- 향후 썸네일 이미지
- S3 호환 SDK, presigned URL, bucket lifecycle 적용 가능

현재 프로젝트에 MinIO가 이미 들어와 있으므로 새 스토리지 제품을 추가할 필요가 없다. 다만 MLflow artifact와 운영 이미지는 성격이 다르므로 bucket을 분리하는 것이 좋다.

예시:

- `mlflow-artifacts`: 기존 MLflow 전용
- `dais-images`: 원본/파생 이미지 전용

### 대안 비교

| 선택지 | 장점 | 단점 | 판단 |
|---|---|---|---|
| PostgreSQL `bytea`에 이미지 직접 저장 | 트랜잭션 단순, 백업 대상 일원화 | DB 비대화, 메모리 사용 증가, 웹 응답 병목, 백업/복구 무거움 | 비권장 |
| PostgreSQL Large Object | 큰 파일 처리 가능 | 별도 삭제/권한 관리 필요, 애플리케이션 복잡도 증가 | 비권장 |
| 파일시스템 경로 + PostgreSQL | 구현 쉬움 | 컨테이너/서버 이동, 백업, 확장성, 권한 관리 어려움 | 개발 단계 임시 |
| MinIO 객체 + PostgreSQL 메타데이터 | 현재 구조와 잘 맞음, 웹/ML 모두 사용 가능, 확장 쉬움 | DB와 객체 정합성 관리 필요 | 권장 |

## 4. 이미지를 DB에 직접 넣을 때의 문제

PostgreSQL의 `bytea`는 바이너리 저장이 가능하지만, 큰 이미지가 많아질수록 운영 부담이 커진다.

주요 문제는 다음과 같다.

- 큰 `bytea` 값은 PostgreSQL TOAST 구조로 분할 저장된다. PostgreSQL 문서에 따르면 큰 값은 압축되거나 별도 TOAST 테이블의 여러 chunk row로 나뉜다.
- 이미지를 조회하면 DB가 chunk를 재조립하고 애플리케이션이 다시 HTTP 응답으로 보내야 한다.
- 웹에서 10장씩 보여줄 때 DB 커넥션, DB shared buffer, API 서버 메모리가 이미지 전송에 같이 묶인다.
- API가 JSON에 base64로 이미지를 실으면 전송량이 약 33% 증가한다.
- DB 백업, 복구, replication, VACUUM 비용이 커진다.
- 이미지 캐싱, range request, CDN/프록시 연동이 object storage 방식보다 불리하다.

PostgreSQL JDBC 문서도 `bytea`가 최대 1GB까지 가능하더라도 매우 큰 binary 값은 처리 시 많은 메모리가 필요하다고 설명한다. Large Object 방식은 큰 값에 더 맞지만, row 삭제와 large object 삭제가 별도라 운영 복잡도가 생긴다.

## 5. 웹 요청 시 얼마나 더 느려질까

정확한 수치는 이미지 크기, 네트워크, DB 메모리, API 구현에 따라 달라서 이 프로젝트 환경에서 별도 벤치마크가 필요하다. 다만 현재 구조 기준으로 예상하면 다음과 같다.

가정:

- 한 페이지에 이미지 10장 표시
- 원본 이미지 1장 1~3MB
- heatmap/annotation까지 같이 보면 이미지당 2~3개 asset 가능
- API 서버가 DB에서 이미지를 읽어 웹에 전달

예상 비교:

| 방식 | 10장 목록 조회 | 10장 이미지 표시 | 특징 |
|---|---:|---:|---|
| PostgreSQL 메타데이터 + MinIO 이미지 URL | DB 조회 수십 ms + 이미지 GET | 대략 수백 ms ~ 2초대 | DB는 가볍고 이미지는 객체 저장소가 처리 |
| PostgreSQL `bytea` + API binary streaming | DB 조회 + TOAST 재조립 + API 전송 | MinIO 방식보다 보통 1.5~3배 느려질 가능성 | DB/API가 이미지 전송 병목 |
| PostgreSQL `bytea` + JSON base64 | DB 조회 + 인코딩 + 33% 전송량 증가 | MinIO 방식보다 2~5배 느려질 가능성 | 가장 비권장 |

특히 결함탐지 화면은 사용자가 페이지를 넘기며 이미지를 반복 조회하는 구조다. DB가 이미지 바이너리까지 직접 서빙하면 모델 추론, 상태 조회, MLflow/Airflow 메타데이터와 같은 중요한 DB 작업까지 같은 자원을 공유하게 된다.

권장 벤치마크:

1. 1MB, 3MB, 5MB 이미지 샘플 각각 100장 준비
2. `bytea` 저장 방식과 MinIO 저장 방식 둘 다 구현한 임시 endpoint 작성
3. `GET /images?page=1&limit=10`과 이미지 10장 동시 로딩을 `hey`, `wrk`, Playwright로 측정
4. p50/p95 latency, API 메모리, Postgres CPU/IO, MinIO latency 비교

## 6. 적용 설계

### 6-1. DB 분리

현재 Postgres 인스턴스는 유지하고 DB만 추가한다.

```sql
CREATE DATABASE dais_data_db;
```

초기 단계에서는 단일 Postgres 인스턴스 안에 DB를 추가하는 방식이 충분하다. 트래픽이 커지면 이미지 메타데이터 DB를 별도 인스턴스로 분리할 수 있다.

### 6-2. 핵심 테이블 초안

```sql
CREATE TABLE cases (
    id UUID PRIMARY KEY,
    case_id TEXT NOT NULL UNIQUE,
    source TEXT,
    status TEXT NOT NULL,
    total_images INTEGER NOT NULL DEFAULT 0,
    defect_count INTEGER NOT NULL DEFAULT 0,
    normal_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE images (
    id UUID PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES cases(id),
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    width INTEGER,
    height INTEGER,
    checksum_sha256 TEXT,
    original_object_key TEXT NOT NULL,
    thumbnail_object_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (case_id, filename)
);

CREATE TABLE inference_runs (
    id UUID PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES cases(id),
    status TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_uri TEXT NOT NULL,
    model_version TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT
);

CREATE TABLE image_predictions (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES inference_runs(id),
    image_id UUID NOT NULL REFERENCES images(id),
    anomaly_score DOUBLE PRECISION NOT NULL,
    is_defect BOOLEAN NOT NULL,
    num_bboxes INTEGER NOT NULL DEFAULT 0,
    bboxes JSONB NOT NULL DEFAULT '[]',
    heatmap_object_key TEXT,
    annotation_object_key TEXT,
    result_json_object_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, image_id)
);
```

페이지네이션은 다음 쿼리로 처리한다.

```sql
SELECT i.*, p.anomaly_score, p.is_defect, p.annotation_object_key
FROM images i
LEFT JOIN image_predictions p ON p.image_id = i.id
WHERE i.case_id = $1
ORDER BY i.created_at, i.filename
LIMIT 10 OFFSET $2;
```

운영 데이터가 많아지면 `OFFSET` 대신 cursor 기반 페이지네이션을 검토한다.

### 6-3. MinIO object key 규칙

```text
dais-images/
  raw/<case_id>/<image_id>/<filename>
  thumb/<case_id>/<image_id>.webp
  result/<case_id>/<run_id>/<image_id>/heatmap.png
  result/<case_id>/<run_id>/<image_id>/annotation.png
  result/<case_id>/<run_id>/<image_id>/result.json
```

object key에는 원본 파일명만 믿지 말고 DB의 UUID를 포함한다. 같은 파일명이 들어와도 충돌을 피할 수 있다.

## 7. 코드 적용 계획

### Phase 1. 문서/인프라 결정

- `docs/ARCHITECTURE.md`의 DB 항목에 `dais_data_db` 추가
- `docker/postgres/init/01-create-databases.sql`에 `CREATE DATABASE dais_data_db;` 추가
- MinIO init에서 `dais-images` bucket 생성
- `.env.example`에 `DATA_DATABASE_URL`, `IMAGE_BUCKET` 추가

### Phase 2. DB 스키마/클라이언트 추가

- `agents/data_agent` 또는 공용 모듈에 DB 연결 코드 추가
- migration 도구 선택: Alembic 권장
- 위 테이블 4개부터 시작
- 이미지 object key 생성 helper 추가

### Phase 3. 업로드/등록 흐름 변경

현재:

```text
data/inference/inbox/<case_id>/이미지 파일
```

변경 후:

```text
홈페이지/API 업로드
  → MinIO raw 업로드
  → Postgres cases/images row 생성
  → case status = READY
```

개발 단계에서는 기존 inbox 폴더를 읽어서 MinIO와 DB에 등록하는 migration/import 스크립트를 먼저 만드는 것이 좋다.

### Phase 4. 추론 API 변경

현재 `POST /predict {"case_id": "..."}`는 폴더를 직접 읽는다. 다음 중 하나로 전환한다.

권장 전환안:

1. `case_id`로 DB에서 이미지 목록 조회
2. MinIO에서 원본 이미지를 임시 작업 디렉터리로 다운로드
3. 기존 `predict_case()` 로직 재사용
4. 생성된 `heatmap.png`, `annotation.png`, `result.json`을 MinIO에 업로드
5. `image_predictions`, `inference_runs`, `cases` 상태 업데이트

이 방식은 현재 모델 코드를 크게 뜯지 않고 저장소만 바꿀 수 있다.

### Phase 5. 홈페이지 API

필요 endpoint 초안:

- `POST /cases`: 케이스 생성
- `POST /cases/{case_id}/images`: 이미지 업로드
- `GET /cases`: 케이스 목록
- `GET /cases/{case_id}/images?limit=10&cursor=...`: 10장 단위 조회
- `POST /cases/{case_id}/predict`: MLflow Production 모델로 추론 요청
- `GET /cases/{case_id}/runs/{run_id}`: 추론 진행 상태
- `GET /images/{image_id}/url?variant=original|thumbnail|heatmap|annotation`: presigned URL 반환

프론트엔드는 이미지 바이너리를 DB API에서 직접 받지 않고, API가 내려준 이미지 URL을 `<img>`에 연결한다.

### Phase 6. Airflow DAG 변경

현재는 inbox 폴더를 스캔한다. 변경 후에는 DB 상태를 스캔한다.

```text
SELECT case_id FROM cases WHERE status = 'READY'
```

처리 완료 후 폴더 이동 대신 상태를 변경한다.

```text
READY → RUNNING → COMPLETED / FAILED
```

## 8. 운영상 주의점

- DB row 생성 성공 후 MinIO 업로드 실패, 또는 반대 상황을 대비해 정합성 복구 job이 필요하다.
- 이미지 삭제는 DB row 삭제와 object 삭제를 같이 처리해야 한다.
- 원본 이미지는 덮어쓰지 말고 immutable하게 저장한다.
- annotation/heatmap은 모델 버전별 결과이므로 `run_id` 아래에 저장한다.
- 홈페이지에서는 원본 대신 thumbnail을 먼저 보여주면 페이지 로딩이 빨라진다.
- 모델 입력은 원본 object를 사용하고, 화면 표시에는 thumbnail/annotation을 사용한다.

## 9. 최종 권장 작업 순서

1. `dais_data_db`와 `dais-images` bucket 추가
2. `cases`, `images`, `inference_runs`, `image_predictions` 테이블 생성
3. 기존 `data/inference/inbox` 케이스를 DB/MinIO에 등록하는 import 스크립트 작성
4. `ml-inference`가 DB/MinIO 기반으로 이미지를 읽고 결과를 저장하도록 adapter 추가
5. 홈페이지용 10장 페이지네이션 API 작성
6. 썸네일 생성 추가
7. Airflow DAG를 폴더 스캔에서 DB 상태 기반으로 변경
8. bytea vs MinIO 방식의 로컬 벤치마크 수행 후 수치 확정

## 10. 참고 자료

- PostgreSQL TOAST: https://www.postgresql.org/docs/current/storage-toast.html
- PostgreSQL binary data type `bytea`: https://www.postgresql.org/docs/current/static/datatype-binary.html
- PostgreSQL Large Object catalog: https://www.postgresql.org/docs/current/catalog-pg-largeobject.html
- PostgreSQL JDBC binary data guidance: https://jdbc.postgresql.org/documentation/binary-data/
- MinIO object storage concepts: https://minio-docs.tf.fo/administration/concepts
- MinIO S3 API compatibility: https://minio-docs.tf.fo/reference/s3-api-compatibility.html
