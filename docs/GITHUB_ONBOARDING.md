# GitHub 협업 온보딩 (신규 팀원용)

> 처음 협업하는 팀원이 **한 번만** 읽으면 되는 가이드.
> 한 줄 요약: `Dais-lab/DaiS-Agent` 는 **Git Flow + PR 필수** 로 협업한다.

협업 규칙 전반은 [CONTRIBUTING.md](CONTRIBUTING.md) 참고.

---

## 0. 30초 그림

```
1. clone        →  로컬에 저장소 받기
2. develop 에서  →  feature/<scope>-<설명> 브랜치 만들기
3. 작업 + commit →  의미있는 단위로 작게 자주
4. push + PR    →  base = develop, 리뷰 1명, CI 통과
5. squash merge →  PR 머지 후 로컬 정리
6. (정기) release/<ver> 로 main 에 반영 (팀 리더 작업)
```

---

## 1. 최초 1회 — 계정 / SSH / 도구

### 1-1. GitHub 계정 등록
- 본인 GitHub 계정으로 `Dais-lab` org 초대 수락
- 2FA 활성화 (org 정책일 가능성)

### 1-2. SSH 키 설정
```bash
# 키가 없다면 생성
ssh-keygen -t ed25519 -C "your_email@example.com"

# 공개키 출력 → GitHub Settings → SSH and GPG keys → New SSH key 에 등록
cat ~/.ssh/id_ed25519.pub

# 연결 테스트
ssh -T git@github.com
# "Hi <username>! You've successfully authenticated..." 확인
```

### 1-3. git 사용자 정보
```bash
git config --global user.name "본인 이름"
# ⚠️ Public repo 라 commit author email 이 영구 공개됨.
#    학교/회사 이메일을 가리고 싶다면 GitHub noreply 이메일 사용:
#    https://github.com/settings/emails 에서
#    "Keep my email addresses private" 체크 후 자동 생성된 주소 복사.
git config --global user.email "<your-id>+<your-username>@users.noreply.github.com"
git config --global init.defaultBranch main
git config --global pull.rebase false   # merge 방식 권장 (rebase 는 추후 합의)
```

### 1-4. 필수 도구
- Docker 24+ / docker compose v2
- Python 3.11+
- `uv` (권장) 또는 `pip`
- `pre-commit` — commit 전 자동 lint/secret 검사

---

## 2. 최초 1회 — repo clone + 환경 셋업

```bash
# 1) clone
git clone git@github.com:Dais-lab/dais-agent-public.git dais_agent
cd dais_agent

# 2) .env 생성 (값은 팀에서 별도 공유받음 — 안전 채널)
make init
$EDITOR .env   # 비밀번호 / API 키 / FERNET_KEY / HOST_* 경로 채우기

# 3) ★ Model training 코드 배치 (ml-* 사용 시 필수)
#    팀 리더에게 패키지 받은 뒤 docs/EXTERNAL_CODE.md 참고.
#    인프라/Agent 만 사용한다면 이 단계는 skip 가능.

# 4) Python 가상환경 (Agent 개발 시)
uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"

# 5) pre-commit hook 등록 (필수)
pre-commit install
# 첫 실행으로 검증
pre-commit run --all-files

# 6) 인프라 기동
make build && make up && make ps
```

검증 URL: [README.md](../README.md) "1. 접속 URL" 표 참고.

---

## 3. 매일 — feature 작업 한 사이클

### 3-1. 최신 develop 받기
```bash
git checkout develop
git pull
```

### 3-2. feature 브랜치 만들기
```bash
git checkout -b feat/<scope>-<짧은-설명>
# 예: feat/data-agent-validate
```

브랜치 명명 규칙 → [CONTRIBUTING.md](CONTRIBUTING.md) "2-1. 브랜치 명명 규칙".

### 3-3. 작업 + commit
```bash
# 변경 후
git add <변경한 파일들>
git commit -m "feat(data-agent): add validate node"
# pre-commit 이 자동 실행됨. 차단되면 메시지 확인 후 수정
```

> **Commit 주기**: 의미있는 작은 단위마다 (=리뷰어가 이해하기 쉬운 크기).
> "WIP" 같은 커밋은 PR 머지 전 squash 되니 부담 갖지 말 것.

### 3-4. push
```bash
git push -u origin feat/data-agent-validate
# 첫 push 시 -u 로 upstream 등록. 이후엔 git push 만
```

### 3-5. PR 만들기 (GitHub 웹)
1. GitHub repo 페이지 → "Compare & pull request" 클릭
2. **Base branch = `develop`** 확인 (중요 — main 아님)
3. PR 템플릿이 자동으로 채워짐 → 항목 작성
4. 리뷰어 지정 (CODEOWNERS 자동, 추가로 도메인 담당자 지정 권장)
5. "Create pull request"

### 3-6. 리뷰 응답 + 머지
- 리뷰 코멘트에 답하거나 추가 commit (자동으로 PR 에 반영됨)
- CI 가 빨강이면 **머지 전 고치기**
- 승인 + CI 통과 시 "Squash and merge" 클릭 (다른 옵션 X)
- 머지 후 본인 feature 브랜치는 자동 삭제됨

### 3-7. 로컬 정리
```bash
git checkout develop
git pull
git branch -d feat/data-agent-validate  # 로컬 정리
```

---

## 4. 트러블슈팅

### Q. push 시 `permission denied (publickey)`
- SSH 키가 GitHub 에 등록 안 됨. 1-2 단계 다시.
- 또는 origin 이 HTTPS 로 잡힌 경우: `git remote set-url origin git@github.com:Dais-lab/dais-agent-public.git`

### Q. pre-commit 이 commit 을 막는다
- 이유 메시지 확인. ruff 가 잡은 lint → 메시지대로 수정.
- gitleaks 가 잡은 secret → **그대로 push 금지**. 코드에서 secret 제거 후 다시 commit.
- 임시로 우회 (권장 X): `git commit --no-verify` — **절대 main/develop 으로 직접 push 시엔 쓰지 말 것**.

### Q. base branch 를 잘못 지정 (main 으로 PR 만듦)
- GitHub PR 페이지에서 "Edit" 버튼으로 base 를 `develop` 으로 변경 가능.

### Q. develop 과 충돌 (conflict) 발생
```bash
git checkout feat/내브랜치
git fetch origin
git merge origin/develop
# 충돌 해결 후
git add <충돌-파일>
git commit -m "merge develop into feat/내브랜치"
git push
```

### Q. 실수로 `.env` 를 staged 했다
- `git restore --staged .env` 또는 `git rm --cached .env`
- 이미 commit 했다면: `git reset --soft HEAD~1` 후 다시 commit (push 전이라면).
- **push 했다면**: 즉시 팀 리더에게 알림 + 해당 키 회전 + git history 정리 필요.

---

## 5. 도와줘 시그널

| 막혔다면 | 어디로 |
|---|---|
| git 명령 모름 | 이 문서 4번 + `git --help <cmd>` |
| Docker / 컨테이너 | [docs/SETUP.md](SETUP.md) |
| 어디 코드를 만져야 할지 | [agents/README.md](../agents/README.md) (Agent) / [docs/MLFLOW_WORKFLOW.md](MLFLOW_WORKFLOW.md) (모델) |
| 결정사항 / 왜 X 아닌 Y | [CLAUDE.md](../CLAUDE.md) "2. 확정된 결정사항" |
| 그래도 안 되면 | GitHub Issues (template 사용) 또는 팀 리더 호출 |

---

## 6. 이 문서를 갱신할 때

신규 팀원이 자주 막히는 지점이 새로 보이면, 본 문서 4번 "트러블슈팅" 에 추가.
근본 규칙 변경은 [CONTRIBUTING.md](CONTRIBUTING.md) 우선.
