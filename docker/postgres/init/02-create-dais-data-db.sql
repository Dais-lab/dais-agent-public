-- 웹 대시보드용 DB (cases, images, inference_runs, image_predictions).
-- 자세한 스키마/도입 배경: docs/IMAGE_STORAGE_REPORT.md, CLAUDE.md Section 6.
--
-- 주의: 이 스크립트는 postgres 볼륨이 비었을 때만 실행된다.
-- 이미 초기화된 볼륨이 있다면 수동으로 CREATE DATABASE 또는 볼륨 삭제 후 재기동.

CREATE DATABASE dais_data_db;
