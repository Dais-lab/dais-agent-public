-- dais_data_db 스키마 (CLAUDE.md Section 6).
-- 적용: docker exec -i dais-postgres psql -U dais_admin -d dais_data_db < scripts/init_data_db_schema.sql
-- 안전하게 멱등 (IF NOT EXISTS).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id TEXT NOT NULL UNIQUE,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'READY',
    total_images INTEGER NOT NULL DEFAULT 0,
    defect_count INTEGER NOT NULL DEFAULT 0,
    normal_count INTEGER NOT NULL DEFAULT 0,
    inspected_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cases_inspected_at ON cases(inspected_at DESC);

CREATE TABLE IF NOT EXISTS images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL DEFAULT 'image/png',
    size_bytes BIGINT NOT NULL DEFAULT 0,
    original_object_key TEXT NOT NULL,
    thumbnail_object_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (case_id, filename)
);
CREATE INDEX IF NOT EXISTS idx_images_case_id ON images(case_id);

CREATE TABLE IF NOT EXISTS inference_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'PENDING',
    model_name TEXT NOT NULL DEFAULT 'dais_anomaly',
    model_uri TEXT NOT NULL DEFAULT 'models:/dais_anomaly/Production',
    model_version TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_inference_runs_case_id ON inference_runs(case_id);

CREATE TABLE IF NOT EXISTS image_predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES inference_runs(id) ON DELETE CASCADE,
    image_id UUID NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    anomaly_score DOUBLE PRECISION NOT NULL,
    is_defect BOOLEAN NOT NULL,
    num_bboxes INTEGER NOT NULL DEFAULT 0,
    bboxes JSONB NOT NULL DEFAULT '[]',
    heatmap_object_key TEXT,
    annotation_object_key TEXT,
    result_json_object_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, image_id)
);
CREATE INDEX IF NOT EXISTS idx_predictions_run_id ON image_predictions(run_id);
CREATE INDEX IF NOT EXISTS idx_predictions_image_id ON image_predictions(image_id);
