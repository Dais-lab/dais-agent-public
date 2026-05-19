// 백엔드(web/backend/schemas.py) 응답 타입과 1:1 매핑.

export interface CaseSummary {
  id: string;
  case_id: string;
  source: string | null;
  status: "READY" | "RUNNING" | "COMPLETED" | "FAILED";
  total_images: number;
  defect_count: number;
  normal_count: number;
  inspected_at: string; // ISO datetime
  created_at: string;
}

export interface ImageRead {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  original_url: string;
}

export interface ImagePage {
  page: number;
  limit: number;
  total: number;
  items: ImageRead[];
}

export interface PredictionRead {
  image_id: string;
  anomaly_score: number;
  is_defect: boolean;
  num_bboxes: number;
  bboxes: unknown[];
  heatmap_url: string | null;
  annotation_url: string | null;
}

export interface RunRead {
  id: string;
  case_id: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";
  model_name: string;
  model_uri: string;
  model_version: string | null;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  predictions: PredictionRead[];
}

export interface PredictResponse {
  run_id: string;
  status: string;
}

export interface DashboardStats {
  total_cases: number;
  total_images: number;
  completed_runs: number;
  defect_images: number;
  failed_runs: number;
  cases_today: number;
}

export interface ServiceStatus {
  name: string;
  url: string;
  ok: boolean;
  latency_ms: number | null;
  error?: string | null;
}

export interface PresignedURLResponse {
  url: string;
  expires_seconds: number;
}
