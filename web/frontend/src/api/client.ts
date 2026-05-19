// 백엔드 API 클라이언트. dev 에서는 Vite proxy 를 통해 /api 가 8005 로 전달됨.
import type {
  CaseSummary,
  DashboardStats,
  ImagePage,
  PredictResponse,
  PresignedURLResponse,
  RunRead,
  ServiceStatus,
} from "./types";

const BASE = ""; // proxy 사용 — same-origin

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status}: ${body}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => jsonFetch<{ status: string }>("/api/health"),
  dashboard: () => jsonFetch<DashboardStats>("/api/dashboard"),
  services: () => jsonFetch<ServiceStatus[]>("/api/services/status"),
  cases: (params?: {
    status?: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
    sort?: "asc" | "desc";
  }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.date_from) q.set("date_from", params.date_from);
    if (params?.date_to) q.set("date_to", params.date_to);
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.sort) q.set("sort", params.sort);
    const qs = q.toString();
    return jsonFetch<CaseSummary[]>(`/api/cases${qs ? "?" + qs : ""}`);
  },
  case: (caseId: string) => jsonFetch<CaseSummary>(`/api/cases/${caseId}`),
  images: (caseId: string, page = 1, limit = 10) =>
    jsonFetch<ImagePage>(`/api/cases/${caseId}/images?page=${page}&limit=${limit}`),
  predict: (caseId: string) =>
    jsonFetch<PredictResponse>(`/api/cases/${caseId}/predict`, { method: "POST" }),
  run: (caseId: string, runId: string) =>
    jsonFetch<RunRead>(`/api/cases/${caseId}/runs/${runId}`),
  latestRun: async (caseId: string): Promise<RunRead | null> => {
    // 케이스의 최근 run 이 없으면 404 → null 로 변환 (새로고침 후 라벨 복원에 사용).
    const res = await fetch(`${BASE}/api/cases/${caseId}/runs/latest`, {
      headers: { "Content-Type": "application/json" },
    });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    return (await res.json()) as RunRead;
  },
  imageUrl: (imageId: string, variant: "original" | "heatmap" | "annotation" = "original") =>
    jsonFetch<PresignedURLResponse>(`/api/images/${imageId}/url?variant=${variant}`),
};

export type { PresignedURLResponse };
