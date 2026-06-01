# CLAUDE.md

DaiS-Agent: DINOv3 이상탐지 + LangGraph 기반 Agent + 웹 대시보드 모노레포.
이 파일은 **진입점**이다. 상세 규칙은 `@.claude/rules/` 로 분할되어 있다.

> 팀 공통 규칙: 사람과 Claude(에이전트) 모두 이 문서와 하위 규칙을 따른다.
> 규칙을 바꾸면 **코드가 아니라 규칙 파일을 먼저 고친다.**

---

## 🚫 절대 금지사항 (commit/push 전 필독)

1. **`.env` 를 commit/push 하지 않는다.** 템플릿은 `.env.example` 에 placeholder(`changeme`)만.
2. **서버 IP·내부 호스트 경로를 코드/문서에 하드코딩하지 않는다.** (예: `/home/...`, 사내 IP) → 항상 환경변수로.
3. **모델 weight(`*.pth`)·원본 이미지·데이터셋을 commit 하지 않는다.**
4. **외부 보관 코드 `model/dinov3_anomaly/` 를 git 에 추가하지 않는다.** (`docs/EXTERNAL_CODE.md`)

> 위는 pre-commit + CI 가 자동 차단한다. 막히면 우회하지 말고 → `@.claude/rules/security.md`

---

## 분할 규칙 (`.claude/rules/`)

@.claude/rules/code-style.md
@.claude/rules/security.md
@.claude/rules/new-agent.md
@.claude/rules/ports.md

## 상세 문서 (`docs/`)

| 주제 | 문서 |
|---|---|
| 기여 가이드 (브랜치/PR/commit) | @docs/CONTRIBUTING.md |
| 디렉토리 구조 | @docs/STRUCTURE.md |
| 아키텍처 | @docs/ARCHITECTURE.md |
| Agent 명세 | @docs/AGENTS.md |
| 포트 할당 표 (SSOT) | @docs/PORTS.md |
| 모델/MLflow 워크플로우 | @docs/MLFLOW_WORKFLOW.md |
| 외부 보관 코드 정책 | @docs/EXTERNAL_CODE.md |
| 개발 환경 셋업 | @docs/SETUP.md |
