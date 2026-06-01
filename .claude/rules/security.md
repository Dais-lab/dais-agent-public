# 보안 규칙 (가장 중요)

> 한 번 push 된 비밀값은 git history 에 영구히 남는다. **막힌 건 우회하지 말고 원인을 고친다.**

## 1. 절대 git 에 올리지 않는 것

| 분류 | 예시 | 올바른 위치 |
|---|---|---|
| 비밀값 | DB 비밀번호, API key, Fernet/secret key, 토큰 | 로컬 `.env` 에만 |
| 서버 주소 | 내부/공인 IP, LLM 서버 주소 | `.env` 의 `LLM_BASE_URL` 등 환경변수 |
| 호스트 절대경로 | `/home/<user>/...`, 사내 마운트 경로 | `.env` 의 `HOST_*` 변수 |
| 모델/데이터 | `*.pth`, 원본 이미지(`png/jpg/bmp/dcm`), 데이터셋 | 추적 제외 (MinIO/MLflow) |
| 외부 코드 | `model/dinov3_anomaly/` | 외부 보관 (`docs/EXTERNAL_CODE.md`) |

## 2. 비밀값·주소는 반드시 환경변수로

- 새 서비스 주소·키가 필요하면 **코드에 박지 말고** `.env.example` 에 placeholder 키만 추가한다.
  ```
  # .env.example  (commit 됨 — placeholder 만)
  NEW_SERVICE_URL=http://<HOST_IP>:9999
  NEW_SERVICE_KEY=changeme
  ```
- 실제 값은 각자 로컬 `.env` 에만 채운다. `.env` 는 `.gitignore` 로 추적 제외돼 있다.
- 코드에서는 `os.environ` / pydantic settings 로 읽는다.

## 3. pre-commit 설치는 필수

처음 클론하면 1회 실행한다:

```bash
uv pip install pre-commit   # 또는 pip install pre-commit
pre-commit install
```

이후 `git commit` 시 자동 검사된다. 수동 전체 검사:

```bash
pre-commit run --all-files
```

검사 항목 (`.pre-commit-config.yaml`): ruff, gitleaks(secret 스캔), detect-private-key,
큰 파일(>1MB) 차단, `model/dinov3_anomaly/`·`*.pth`·원본 데이터 commit 차단.

## 4. CI 가 자동으로 막는 것

PR/푸시 시 GitHub Actions 가 돌며, 걸리면 **머지 불가**다 (`.github/workflows/secrets-scan.yml`):

- **TruffleHog**: 실제 유효한 secret 탐지 (`--only-verified --fail`)
- **금지 파일 차단**: `.env`(`.env.example` 제외), weights, 원본 데이터, 외부 코드
- **서버 IP / 호스트 경로 누출 차단**: 알려진 내부 IP·호스트 절대경로가 코드/문서에 있으면 실패

## 5. 실수로 commit 했다면

- **아직 push 안 함**: `git rm --cached <file>` 후 `.gitignore` 확인, commit 수정.
- **이미 push 함**: 노출된 secret 은 **즉시 폐기·재발급**한다 (history 에서 지워도 유출로 간주).
  history 정리(`git filter-repo` 등)는 팀 리더와 협의.

연관: `@.claude/rules/workflow.md`, `@.claude/rules/new-agent.md`
