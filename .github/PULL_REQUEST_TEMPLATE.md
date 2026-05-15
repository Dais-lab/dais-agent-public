## 무엇을

<!-- 변경 내용을 1~3줄로. 무엇이 바뀌었는지 한눈에 보이도록 -->

## 왜

<!-- 이 변경의 이유 / 어떤 결정에 따른 것인지 / 어떤 이슈 해결인지 -->
<!-- 관련 이슈가 있으면: Closes #123 -->

## 어떻게 테스트했나

- [ ] `make up` 후 수동 검증
- [ ] 단위 테스트 추가/통과 (`pytest tests/unit/`)
- [ ] 통합 테스트 (해당 시): `pytest -m integration`
- [ ] LangSmith trace 확인 (Agent 변경 시)
- [ ] UI/API 직접 호출로 확인 (해당 시)

## 영향 범위

<!-- 다른 컴포넌트에 영향이 있는지. 예: docker compose 재빌드 필요 여부, .env 변경 필요 여부 -->

## 문서 갱신

- [ ] 결정 변경 시 `docs/ARCHITECTURE.md` 갱신
- [ ] 포트 변경 시 `docs/PORTS.md` 갱신
- [ ] Agent 입출력 변경 시 `docs/AGENTS.md` 갱신
- [ ] 새 환경변수 시 `.env.example` 갱신
- [ ] 의존성 변경 시 `pyproject.toml` 또는 해당 컨테이너 requirements 갱신

## 체크리스트 (병합 전)

- [ ] `.env` / `model/weights/` / `data/` 가 실수로 staged 되지 않았다
- [ ] base branch 가 `develop` (또는 hotfix 시 `main`) 이다
- [ ] CI (lint + secret scan) 통과
- [ ] 리뷰어 지정 완료
