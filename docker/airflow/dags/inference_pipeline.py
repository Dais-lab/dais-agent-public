"""DINOv3 anomaly inference 배치 DAG.

흐름:
  1) data/inference/inbox/ 스캔 → 처리 안 된 case_id 폴더 목록
  2) 각 case 마다 ml-inference (FastAPI :8004) 의 POST /predict 호출
  3) 처리 완료된 케이스를 inbox/<case> → archive/<case> 로 이동

전제 조건:
  - ml-inference 컨테이너 기동 중 (`make ml-up`)
  - 같은 docker network (dais_network) 에 있어 hostname 'ml-inference' 로 접근 가능

수동 트리거 (schedule=None). 사람이 inbox 에 데이터 떨어뜨린 후 Airflow UI 에서 실행.
운영에서 정기 폴링 원하면 schedule="*/10 * * * *" 등으로 변경.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

INBOX = "/opt/dais/data/inference/inbox"
ARCHIVE = "/opt/dais/data/inference/archive"
ML_INFERENCE_URL = "http://ml-inference:8004"
EXCLUDE_PREFIXES = ("_", ".")  # _smoke_test, .hidden 등 무시


def _list_pending_cases() -> list[str]:
    if not os.path.isdir(INBOX):
        return []
    cases: list[str] = []
    for name in sorted(os.listdir(INBOX)):
        if name.startswith(EXCLUDE_PREFIXES):
            continue
        if not os.path.isdir(os.path.join(INBOX, name)):
            continue
        cases.append(name)
    return cases


def _scan(**ctx) -> list[str]:
    cases = _list_pending_cases()
    print(f"Pending cases ({len(cases)}): {cases}")
    ctx["ti"].xcom_push(key="cases", value=cases)
    return cases


def _run_inference(**ctx) -> None:
    import requests  # airflow base 에 있지만 명시적 의존성은 requirements.txt

    cases = ctx["ti"].xcom_pull(task_ids="scan_inbox", key="cases") or []
    if not cases:
        print("No pending cases — nothing to do.")
        return

    failures: list[tuple[str, str]] = []
    for case_id in cases:
        try:
            print(f"[{case_id}] POST {ML_INFERENCE_URL}/predict")
            resp = requests.post(
                f"{ML_INFERENCE_URL}/predict",
                json={"case_id": case_id},
                timeout=3600,  # 큰 케이스 대비 1시간
            )
            resp.raise_for_status()
            meta = resp.json()
            summary = meta.get("summary", {})
            print(
                f"[{case_id}] defect={summary.get('defect')} / "
                f"total={summary.get('total')}"
            )

            # archive 이동
            src = os.path.join(INBOX, case_id)
            dst = os.path.join(ARCHIVE, case_id)
            os.makedirs(ARCHIVE, exist_ok=True)
            if os.path.exists(dst):
                ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                dst = f"{dst}_{ts}"
            shutil.move(src, dst)
            print(f"[{case_id}] archived → {dst}")
        except Exception as exc:  # noqa: BLE001
            print(f"[{case_id}] FAILED: {type(exc).__name__}: {exc}")
            failures.append((case_id, str(exc)))

    if failures:
        raise RuntimeError(
            f"{len(failures)} cases failed: {[f[0] for f in failures]}"
        )


with DAG(
    dag_id="inference_pipeline",
    description="inbox 케이스를 ml-inference API 로 처리하고 archive 로 이동",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
        "execution_timeout": timedelta(hours=4),
    },
    tags=["mlops", "inference"],
) as dag:
    scan = PythonOperator(task_id="scan_inbox", python_callable=_scan)
    run = PythonOperator(task_id="run_inference", python_callable=_run_inference)
    scan >> run
