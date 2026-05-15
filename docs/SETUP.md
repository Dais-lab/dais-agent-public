# 상세 설치 가이드

> 빠른 시작은 [README.md](../README.md) 의 Quick Start 참고.
> 본 문서는 트러블슈팅과 단계별 검증 방법을 담는다.

---

## 1. 사전 요구사항

| 항목 | 버전 | 설치 확인 |
|---|---|---|
| Docker | 24+ | `docker --version` |
| Docker Compose | v2 (plugin) | `docker compose version` |
| Make | 3.81+ | `make --version` |
| Python | 3.11+ | `python --version` (Phase 4 이후 필요) |
| uv (선택) | 최신 | `uv --version` (Phase 4 이후) |

> Docker Desktop 사용자는 plugin 이 함께 설치되어 있다.
> Linux 사용자는 `docker-compose-plugin` 패키지를 별도 설치.

---

## 2. 환경변수 설정

```bash
make init     # .env 파일 생성 (.env.example 복사)
```

`.env` 파일에서 반드시 변경할 항목:

| 키 | 비고 |
|---|---|
| `POSTGRES_PASSWORD` | 기본값 `changeme` |
| `MINIO_ROOT_PASSWORD` | 기본값 `changeme` |
| `AWS_SECRET_ACCESS_KEY` | MinIO 비밀번호와 동일하게 |
| `AIRFLOW__WEBSERVER__SECRET_KEY` | 임의의 긴 문자열 |
| `AIRFLOW__CORE__FERNET_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 로 생성 |
| `LANGCHAIN_API_KEY` | LangSmith 키 (트레이싱 사용 시) |

---

## 3. 기동 (Phase 2 완료 후 실제 동작)

```bash
make up           # 백그라운드 기동
make ps           # 상태 확인
make logs         # 로그 follow (Ctrl+C 로 빠져나가도 컨테이너는 계속 동작)
```

### 헬스체크
모든 서비스에 `healthcheck` 가 정의되어 있어 `make ps` 결과의 `STATUS` 컬럼에 `healthy` 가 표시되어야 한다. 일부 서비스(Airflow init, MinIO 버킷 생성)는 한 번 실행 후 종료되는 init 컨테이너이다.

---

## 4. 검증

### MLflow
```bash
curl -fsS http://localhost:5000/health
# 또는 브라우저: http://localhost:5000
```

### Airflow
```bash
curl -fsS http://localhost:8080/health
# 브라우저: http://localhost:8080  (기본 ID/PW 는 docker-compose 에서 설정)
```

### MinIO
```bash
# Console: http://localhost:9001
# 로그인: MINIO_ROOT_USER / MINIO_ROOT_PASSWORD
```

### Grafana
```bash
# http://localhost:3000  (기본 admin/admin)
```

### Postgres
```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U $POSTGRES_USER -c '\l'
# mlflow_db, airflow_db 둘 다 존재해야 함
```

---

## 5. 트러블슈팅

> 실제 이슈가 발생하면 본 섹션에 누적 기록한다.

### Q. `make up` 후 MLflow 가 죽는다
- Postgres 가 완전히 뜨기 전에 MLflow 가 연결 시도. 기본 healthcheck 가 잡아주지만 로컬 부하 시 실패 가능.
- 해결: `make restart` 또는 `docker compose restart mlflow`.

### Q. 포트 충돌 (5000 / 8080 / 3000 등)
- 이미 다른 서비스가 사용 중. `docker-compose.dev.yml` 에서 포트 매핑만 바꿔서 띄울 것.
- macOS Control Center 가 5000 사용 → 시스템 설정에서 비활성화 또는 5001 매핑.

### Q. MinIO 버킷이 안 만들어진다
- init 컨테이너 로그 확인: `docker compose logs minio-init`
- 수동: MinIO Console 에서 `mlflow-artifacts` 버킷 생성.

---

## 6. 완전 초기화

```bash
make clean        # 컨테이너 + 볼륨 모두 삭제 (데이터 영구 손실)
make up
```
