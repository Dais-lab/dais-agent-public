-- cases.defect_count / normal_count 를 "가장 최근 COMPLETED run" 기준으로 재계산.
--
-- 배경: 초기 _update_case_counts 가 케이스의 모든 COMPLETED run 의 예측을 합산하여,
-- 같은 케이스에서 결함 탐지를 N번 실행하면 카운트가 누적되었음
-- (예: 이미지 10장 케이스의 결함이 22로 표시되는 현상).
--
-- 실행:
--   docker exec -i dais-postgres psql -U dais -d dais_data_db \
--     < scripts/recompute_case_counts.sql

BEGIN;

WITH latest_run AS (
    SELECT DISTINCT ON (case_id)
        case_id,
        id AS run_id
    FROM inference_runs
    WHERE status = 'COMPLETED'
    ORDER BY case_id, finished_at DESC NULLS LAST, started_at DESC NULLS LAST
),
agg AS (
    SELECT
        lr.case_id,
        COUNT(*) FILTER (WHERE ip.is_defect IS TRUE)  AS defect_count,
        COUNT(*) FILTER (WHERE ip.is_defect IS FALSE) AS normal_count
    FROM latest_run lr
    JOIN image_predictions ip ON ip.run_id = lr.run_id
    GROUP BY lr.case_id
)
UPDATE cases c
SET defect_count = COALESCE(agg.defect_count, 0),
    normal_count = COALESCE(agg.normal_count, 0),
    updated_at   = now()
FROM agg
WHERE c.id = agg.case_id;

-- 한 번도 COMPLETED 된 적 없는 케이스는 0 으로 정리 (이전에 잘못 누적된 값 제거)
UPDATE cases c
SET defect_count = 0,
    normal_count = 0,
    updated_at   = now()
WHERE NOT EXISTS (
    SELECT 1 FROM inference_runs r
    WHERE r.case_id = c.id AND r.status = 'COMPLETED'
)
AND (c.defect_count <> 0 OR c.normal_count <> 0);

COMMIT;

-- 검증용 쿼리 (선택)
SELECT case_id, status, total_images, defect_count, normal_count
FROM cases
ORDER BY inspected_at DESC
LIMIT 10;
