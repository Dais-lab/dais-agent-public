-- Postgres 컨테이너 최초 기동 시 1회만 실행됨.
-- MLflow, Airflow 가 사용할 두 개의 DB 를 분리 생성한다.
--
-- 주의: 이 스크립트는 데이터 디렉토리가 비어있을 때만 실행된다.
-- 이미 초기화된 볼륨이 남아있으면 실행되지 않으므로,
-- 변경 적용 시 postgres 볼륨 삭제 후 재기동 필요.

CREATE DATABASE mlflow_db;
CREATE DATABASE airflow_db;
