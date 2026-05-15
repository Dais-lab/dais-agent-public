# 외부 보관 코드 — Model training 코드

본 저장소는 **인프라 + Agent 골격 + 학습/추론 wrapper** 까지만 포함한다.
실제 DINOv3 anomaly 학습/추론 응용 코드 (`model/dinov3_anomaly/`) 는
**저장소에 포함하지 않으며, 호스트의 별도 경로에 보관** 한다.

---

## 1. 왜 분리되어 있는가

- 본 코드 자산을 외부에 노출하지 않기 위함 (라이선스: All Rights Reserved)
- 코드 작성자의 IP/저작권 보호
- 본 저장소가 public 이라도 핵심 학습 코드는 비공개 유지

---

## 2. 운용 방식 — 호스트 보관 + 자동 복사

```
[호스트 보관소]
${HOST_DINOV3_PKG}                            기본값: /dais02/dinov3_anomaly
  ↓
[make ml-* 가 자동 호출]
make ml-prepare  → cp -r 로 model/dinov3_anomaly/ 에 복사
  ↓
[저장소 작업 폴더 (gitignore 처리)]
model/dinov3_anomaly/
  ↓
[컨테이너 마운트 — docker-compose 의 ../model:/opt/dais/code/model:rw]
/opt/dais/code/model/dinov3_anomaly/
```

→ 팀원이 수동으로 cp / symlink 할 필요 없음. `make ml-*` 가 자동.

---

## 3. 받는 절차 (신규 팀원 onboarding)

### Step 1. 호스트의 보관 경로 확인
공용 서버에 이미 배치되어 있다면 (예: `/dais02/dinov3_anomaly/`) 추가 작업 없음.
없다면 팀 리더에게 요청.

### Step 2. `.env` 의 경로 확인
```
HOST_DINOV3_PKG=/dais02/dinov3_anomaly
```
기본값이 위와 같이 설정되어 있음. 본인 환경에 맞게 수정 가능.

### Step 3. ml-* 명령 실행
```bash
make ml-build       # 내부적으로 ml-prepare 자동 호출 → cp → docker build
make ml-up          # 동일하게 ml-prepare → docker up
make ml-train       # 학습
make ml-predict CASE=<case_id>
```

→ 별도 수동 단계 없음.

---

## 4. 동작/비동작 매트릭스

| 명령 / 기능 | 호스트 코드 없이 | 호스트 코드 있고 |
|---|---|---|
| `make up` / `make ps` | ✅ 동작 | ✅ 동작 |
| Agent 컨테이너 (8001/8002/8003 `/health`) | ✅ 동작 | ✅ 동작 |
| MLflow / Airflow / Grafana UI | ✅ 동작 | ✅ 동작 |
| `make ml-build` | ❌ 친절한 에러 | ✅ 동작 |
| `make ml-up` | ❌ 친절한 에러 | ✅ 동작 |
| `make ml-train` / `ml-predict` / `ml-register-existing` | ❌ 친절한 에러 | ✅ 동작 |

→ 외부 fork 받은 사람은 `ml-*` 만 못 함 (의도된 차단). 인프라/Agent 골격은 자유롭게 학습 가능.

---

## 5. 보안 규칙

- `model/dinov3_anomaly/` 는 **git 에 절대 commit 하지 말 것**.
- 4중 안전장치 (모두 자동 작동):
  1. `.gitignore` — staged 대상에서 제외
  2. `.pre-commit-config.yaml` — `block-external-training-code` hook 이 commit 차단
  3. `.github/workflows/secrets-scan.yml` — push/PR 시 CI 가 차단
  4. `git add -f` 강제도 위 hook 이 막음
- 만약 실수로 commit + push 했다면 즉시 팀 리더에게 알림.

---

## 6. 트러블슈팅

### Q. `make ml-build` 시 `❌ /dais02/dinov3_anomaly 가 없습니다`
- 호스트 보관 경로가 비어있음. 팀 리더에게 받거나 `.env` 의 `HOST_DINOV3_PKG` 경로를 본인 환경에 맞게 수정.

### Q. `make ml-build` 자체는 성공했는데 컨테이너 안 `/opt/dais/code/model/dinov3_anomaly/` 가 비어있음
- 거의 발생 안 함 (ml-prepare 가 cp 함). 단 직접 `docker compose ... build` 를 호출했다면 ml-prepare 가 안 돈 것 → `make ml-build` 사용 권장.

### Q. 호스트 보관소의 코드를 업데이트했는데 컨테이너에 반영 안 됨
- `make ml-build` 또는 `make ml-up` 다시 실행 (cp 재실행 → 최신 반영).

### Q. `HOST_DINOV3_BACKBONE` 경로가 빈 폴더로 마운트됨
- `.env` 에 경로 미설정. `facebookresearch/dinov3` 를 git clone 한 호스트 경로로 설정 필요. 이건 ml-prepare 와 다른 경로 (백본 vs 응용 코드).
