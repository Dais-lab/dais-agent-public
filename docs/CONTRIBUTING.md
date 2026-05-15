# 협업 가이드

> 본 문서는 dais_agent 프로젝트에서 **팀원이 코드/문서를 변경할 때 지켜야 할 규칙** 을 모은다.
> 새 합류자는 처음 PR 올리기 전에 한 번 읽어주세요.

---

## 1. 작업 규칙 (반드시)

### 1-1. 결정 변경 시 문서 우선
- 시스템 구성/포트/모델/Agent 책임 등 **결정이 바뀌면 코드보다 문서 먼저 갱신**.
- 결정 배경은 [docs/ARCHITECTURE.md](ARCHITECTURE.md) "2. 확정된 결정사항" 에 한 줄 추가.

### 1-2. 포트 추가/변경 시
- 반드시 [docs/PORTS.md](PORTS.md) 의 표를 동시 갱신.
- 8080 (Airflow) / 9000~9001 (MinIO) 등 점유 포트와 충돌 피할 것. 새 Agent/서비스는 8000번대 사용.

### 1-3. 새 환경변수 추가 시
- 반드시 `.env.example` 에 같이 추가 (placeholder 값으로).
- 실제 값(비밀번호/API 키)은 절대 git 에 커밋하지 말 것.

### 1-4. 보안 / 비밀
- `.env` / `weights/*.pth` / 데이터(`data/`) / `model/dinov3_anomaly/` — 모두 `.gitignore` 처리되어 있음. **`git add -f` 등으로 강제 추가 금지**.
- pre-commit hook (`block-external-training-code`) 과 CI workflow 가 차단함.
- LangSmith API key / HuggingFace 토큰 등은 환경변수로만.
- 실수로 비밀이 커밋되면 즉시 키 회전 후 git 히스토리 정리.
- Model training 코드 (외부 보관) 는 [docs/EXTERNAL_CODE.md](EXTERNAL_CODE.md) 참고.

### 1-5. Agent 로직 변경 시
- `docs/AGENTS.md` 의 입출력 스키마부터 갱신.
- 입출력 스키마는 Pydantic 모델로 명시 (필드명/타입/필수 여부/예시).

---

## 2. Git 워크플로 (Git Flow)

신규 팀원은 먼저 [GITHUB_ONBOARDING.md](GITHUB_ONBOARDING.md) 의 단계별 가이드를 한 번 읽으세요.

> **참고**: 본 저장소는 GitHub branch protection 룰셋이 활성화되어 있습니다.
> `main` / `develop` 으로의 직접 push 는 차단되며, PR + 리뷰 + CI 통과를 거쳐야 머지됩니다.

### 2-0. 브랜치 모델 한눈에

```
main         ●─────────────●──────────●──▶  태그된 안정 버전만
              ↑             ↑          ↑
              release       release    hotfix
              │             │          │
develop  ●─●─●─●─●─●─●─●─●─●─●─●─●─●─●─●──▶ 모든 PR 의 base
          ↑ ↑     ↑   ↑
          │ │     │   │
       feat/A  feat/B  fix/C
```

| 브랜치 | base | 머지 대상 | 누가 만드나 | 보호 |
|---|---|---|---|---|
| `main` | — | (자동 머지 X, release/hotfix 만) | 초기 1회 | 리뷰 2명 + CI |
| `develop` | main | (release 통해 main 으로) | 초기 1회 | 리뷰 1명 + CI |
| `feature/<scope>-<설명>` | develop | develop (PR) | 작업자 | — |
| `fix/<scope>-<설명>` | develop | develop (PR) | 작업자 | — |
| `release/v<버전>` | develop | main + develop | 팀 리더 | — |
| `hotfix/<scope>-<설명>` | main | main + develop | 긴급 시 | — |

> **원칙**: 일상 작업은 모두 `develop` 을 base 로. `main` 은 **release/hotfix 만** 머지 가능.

### 2-1. 브랜치 명명 규칙

```
<type>/<scope>-<짧은-설명>
```

| type | 의미 | base | 예 |
|---|---|---|---|
| `feat` | 새 기능 | develop | `feat/data-agent-validate` |
| `fix` | 버그 수정 | develop | `fix/airflow-dag-timeout` |
| `refactor` | 리팩토링 | develop | `refactor/llm-client` |
| `docs` | 문서만 | develop | `docs/update-mlflow-workflow` |
| `chore` | 빌드/도구 | develop | `chore/bump-langchain` |
| `test` | 테스트 추가 | develop | `test/inference-postprocess` |
| `release` | 릴리스 안정화 | develop | `release/v0.2.0` |
| `hotfix` | 운영 긴급 수정 | main | `hotfix/llm-key-leak` |

### 2-2. 일상 사이클 (feature 작업)

```bash
# 1. 최신 develop
git checkout develop && git pull

# 2. 새 브랜치 (base = develop)
git checkout -b feat/data-agent-validate

# 3. 작업 + 작은 단위로 commit (pre-commit 이 lint/secret 자동 검사)
git add <변경된 파일들>
git commit -m "feat(data-agent): add validate node for inbox cases"

# 4. push + PR (base 는 반드시 develop)
git push -u origin feat/data-agent-validate
# GitHub 웹에서 "Compare & pull request" → base: develop

# 5. 리뷰 통과 + CI 그린 → "Squash and merge"
# 6. 로컬 정리
git checkout develop && git pull
git branch -d feat/data-agent-validate
```

### 2-3. release 사이클 (팀 리더)

```bash
# 1. develop 에서 release 브랜치 따기
git checkout develop && git pull
git checkout -b release/v0.2.0

# 2. 버전 bump (pyproject.toml 등), 마무리 작업
# 3. PR: release/v0.2.0 → main (리뷰 2명 + CI)
# 4. main 머지 후 태그
git checkout main && git pull
git tag -a v0.2.0 -m "Release v0.2.0"
git push origin v0.2.0
# 5. main 의 변경을 develop 으로 back-merge
git checkout develop && git pull
git merge main && git push
```

### 2-4. hotfix (운영 긴급)

```bash
# 1. main 에서 hotfix 브랜치
git checkout main && git pull
git checkout -b hotfix/llm-key-leak

# 2. 수정 + commit + push + PR
# 3. PR 1: hotfix → main (긴급 머지)
# 4. PR 2: hotfix → develop (동일 변경 반영)
```

### 2-5. Commit 메시지 형식

```
<type>(<scope>): <짧은 설명>

(선택) 자세한 설명 — 왜 이 변경이 필요한지
```

예시:
- `feat(data-agent): add validate node for inbox cases`
- `fix(ml-inference): handle missing meta.json`
- `docs(ports): add 8004 ml-inference`
- `chore(makefile): pin project name to dais`

---

## 3. PR 가이드

### 3-1. PR 본문
PR 본문은 `.github/PULL_REQUEST_TEMPLATE.md` 가 자동으로 채워준다. 항목을 빠짐없이 작성할 것.

### 3-2. 리뷰 체크리스트 (리뷰어용)

- [ ] base branch 가 `develop` (hotfix/release 외) 인가?
- [ ] `.env` / `model/weights/` / `data/` 가 실수로 staged 되지 않았나?
- [ ] 새 의존성이 `pyproject.toml` 또는 해당 컨테이너 requirements 에 추가됐나?
- [ ] 새 포트가 [docs/PORTS.md](PORTS.md) 에 등록됐나?
- [ ] 컨테이너 mount/compose 변경 시 "down + up" 권고 메모가 있나?
- [ ] 결정 변경 시 [docs/ARCHITECTURE.md](ARCHITECTURE.md) 갱신됐나?
- [ ] Agent 입출력 변경 시 [docs/AGENTS.md](AGENTS.md) 갱신됐나?
- [ ] CI (lint + secret scan) 그린인가?

### 3-3. 머지 정책
- **Squash and merge** 만 사용 (history 단순화)
- 머지 후 브랜치 자동 삭제 (GitHub 설정)
- main / develop 으로의 직접 push 금지 (브랜치 보호 규칙)

---

## 3-A. pre-commit (필수)

로컬 commit 전 자동 검사. 신규 팀원은 clone 직후 반드시 1회 등록:

```bash
pip install pre-commit       # 또는 uv pip install pre-commit
pre-commit install
# 첫 검증
pre-commit run --all-files
```

검사 항목 (`.pre-commit-config.yaml`):
- ruff (Python lint)
- merge conflict / EOF / trailing whitespace
- 1MB 초과 파일 차단 (weights/data 실수 방지)
- detect-private-key
- gitleaks (secret 패턴 스캔)

---

## 4. 환경 동기화

### 4-1. 의존성 변경된 PR 이 머지된 후

```bash
git pull
uv sync                     # 본인 venv (또는 pip install -e ".[dev]")
make build                  # 컨테이너 이미지에도 새 의존성 반영
make up
```

### 4-2. 마운트 / compose 변경된 PR

```bash
git pull
make down                   # 옛 마운트 컨테이너 destroy
make up                     # 새 마운트로 재생성
```

### 4-3. 단순 코드 변경

| 폴더 | 반영 방법 |
|---|---|
| `agents/` | Dockerfile 의 `COPY` 라 **rebuild 필요** (`make build && make up`) |
| `model/` | 호스트 마운트라 즉시 반영. ml-inference 의 모델 재로드는 `curl POST /reload` |
| `docker/airflow/dags/` | 호스트 마운트라 즉시 반영 |
| `docs/`, `*.md` | 컨테이너와 무관, 작업 불필요 |

---

## 5. 같은 컨테이너 / 같은 머신에서 둘 이상이 작업할 때

| 상황 | 해결 |
|---|---|
| 두 명이 같은 파일 동시 수정 | git branch 분리 + merge/rebase 로 해결 |
| 한 머신 공유, 컨테이너 포트 충돌 | `infra/docker-compose.dev.yml` 오버라이드로 포트 분리 / 또는 시간 분리 |
| 같은 컨테이너 안에서 같이 디버깅 | `docker exec ...` 으로 여러 셸 동시 진입 가능 |
| pair 작업 시 | git branch 동일 + 한 명이 push, 한 명이 fetch + reset |

> **외워둘 한 문장**: "컨테이너는 환경, 협업은 git. 두 사람은 같은 git 저장소에서 만난다."

---

## 6. 자주 발생하는 트러블

| 증상 | 원인 / 해결 |
|---|---|
| `compose ... name "/dais-xxx" already in use` | 옛 컨테이너 잔존. `docker rm -f <name>` 또는 `docker compose -p <old_project> down` |
| `port is already allocated` | 호스트 포트 충돌. `docs/PORTS.md` 의 충돌 회피 규칙 참고 |
| `docker-compose.yml volume already exists for project "..."` | project name 변경. `docker volume ls` 로 확인 후 일치시키기 |
| LLM 응답이 이상하다 | LangSmith dashboard 에서 trace 확인 — `dais_agent` 프로젝트 |
| GPU OOM | `--gpu-memory-utilization` 조정 또는 다른 GPU 점유 프로세스 확인 (`nvidia-smi`) |

---

## 7. 더 자세한 정보

| 무엇이 알고 싶을 때 | 어디 |
|---|---|
| **GitHub 협업 첫 시작 (신규 팀원)** | [docs/GITHUB_ONBOARDING.md](GITHUB_ONBOARDING.md) |
| 시스템 결정 배경 / 다이어그램 | [docs/ARCHITECTURE.md](ARCHITECTURE.md) |
| 파일 구조 상세 | [docs/STRUCTURE.md](STRUCTURE.md) |
| 포트 표 | [docs/PORTS.md](PORTS.md) |
| 설치 / 트러블슈팅 | [docs/SETUP.md](SETUP.md) |
| MLflow 흐름 | [docs/MLFLOW_WORKFLOW.md](MLFLOW_WORKFLOW.md) |
| Agent 책임 / 입출력 | [docs/AGENTS.md](AGENTS.md) |
| Agent 개발 온보딩 | [agents/README.md](../agents/README.md) |
| 데이터 컨벤션 | [data/README.md](../data/README.md) |
