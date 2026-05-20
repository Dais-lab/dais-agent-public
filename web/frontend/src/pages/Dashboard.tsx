import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { CaseSummary, DashboardStats, ServiceStatus } from "../api/types";
import Icon from "../components/Icon";
import StatusBadge from "../components/StatusBadge";
import ExampleBadge from "../components/ExampleBadge";

const EXTERNAL_LINKS = [
  { name: "Airflow", url: "http://203.250.72.36:8080", icon: "schedule", color: "bg-sky-500" },
  { name: "MLflow", url: "http://203.250.72.36:5000", icon: "deployed_code", color: "bg-indigo-500" },
  { name: "Grafana", url: "http://203.250.72.36:3000", icon: "monitoring", color: "bg-orange-500" },
  { name: "MinIO", url: "http://203.250.72.36:9001", icon: "database", color: "bg-rose-500" },
];

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [services, setServices] = useState<ServiceStatus[] | null>(null);
  const [recent, setRecent] = useState<CaseSummary[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.dashboard(), api.services(), api.cases({ limit: 5 })])
      .then(([s, sv, cs]) => {
        setStats(s);
        setServices(sv);
        setRecent(cs);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-on-surface">대시보드</h1>
        <p className="mt-1 text-sm text-on-surface-variant">
          MLOps 운영 현황 한눈에 보기 — 외부 서비스, 케이스 현황, 시스템 상태
        </p>
      </div>

      {err && (
        <div className="rounded-lg border border-error-container bg-error-container/30 px-4 py-3 text-sm text-on-error-container">
          백엔드 연결 실패: {err}
        </div>
      )}

      {/* 외부 서비스 링크 카드 */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-on-surface-variant">외부 서비스</h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {EXTERNAL_LINKS.map((s) => (
            <a
              key={s.name}
              href={s.url}
              target="_blank"
              rel="noreferrer"
              className="group flex items-center gap-3 rounded-xl border border-outline-variant bg-surface-container-lowest p-4 shadow-card transition-all hover:border-primary hover:shadow-md"
            >
              <div className={`grid h-10 w-10 place-items-center rounded-lg ${s.color} text-white`}>
                <Icon name={s.icon} size={22} />
              </div>
              <div className="flex-1">
                <div className="text-sm font-semibold text-on-surface">{s.name}</div>
                <div className="font-mono text-[11px] text-on-surface-variant">{s.url.replace("http://", "")}</div>
              </div>
              <Icon
                name="open_in_new"
                size={18}
                className="text-on-surface-variant group-hover:text-primary"
              />
            </a>
          ))}
        </div>
      </section>

      {/* 핵심 지표 */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-on-surface-variant">핵심 지표</h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Kpi label="총 케이스" value={stats?.total_cases} icon="folder" />
          <Kpi label="총 이미지" value={stats?.total_images} icon="image" />
          <Kpi
            label="결함 이미지"
            value={stats?.defect_images}
            icon="report"
            accent="text-error"
          />
          <Kpi label="실패 작업" value={stats?.failed_runs} icon="error" accent="text-tertiary" />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* 서비스 상태 */}
        <section className="lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold text-on-surface-variant">서비스 상태</h2>
          <div className="overflow-hidden rounded-xl border border-outline-variant bg-surface-container-lowest">
            <table className="w-full text-sm">
              <thead className="bg-surface-container-low text-on-surface-variant">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">서비스</th>
                  <th className="px-4 py-2 text-left font-medium">URL</th>
                  <th className="px-4 py-2 text-left font-medium">상태</th>
                  <th className="px-4 py-2 text-right font-medium">응답시간</th>
                </tr>
              </thead>
              <tbody>
                {!services && (
                  <tr>
                    <td colSpan={4} className="px-4 py-6 text-center text-on-surface-variant">
                      불러오는 중...
                    </td>
                  </tr>
                )}
                {services?.map((s) => (
                  <tr key={s.name} className="border-t border-outline-variant">
                    <td className="px-4 py-2 font-medium text-on-surface">{s.name}</td>
                    <td className="px-4 py-2 font-mono text-[12px] text-on-surface-variant">
                      {s.url}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${
                          s.ok
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-error-container text-on-error-container"
                        }`}
                      >
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${
                            s.ok ? "bg-emerald-500" : "bg-error"
                          }`}
                        />
                        {s.ok ? "정상" : "오류"}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-[12px] text-on-surface-variant">
                      {s.latency_ms != null ? `${s.latency_ms} ms` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* 일별 결함률 추이 (예시) */}
        <section>
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-on-surface-variant">
            일별 결함률 추이 <ExampleBadge />
          </h2>
          <div className="flex h-full min-h-[200px] flex-col gap-2 rounded-xl border border-outline-variant bg-surface-container-lowest p-4">
            <div className="flex items-end gap-1.5">
              {[42, 58, 35, 71, 49, 62, 38, 81, 55, 67, 44].map((v, i) => (
                <div
                  key={i}
                  className="flex-1 rounded-t bg-primary/60"
                  style={{ height: `${v}%` }}
                  title={`${v}%`}
                />
              ))}
            </div>
            <div className="mt-auto text-[11px] text-on-surface-variant">최근 11일</div>
          </div>
        </section>
      </div>

      {/* 최근 케이스 */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-on-surface-variant">최근 케이스</h2>
        <div className="overflow-hidden rounded-xl border border-outline-variant bg-surface-container-lowest">
          <table className="w-full text-sm">
            <thead className="bg-surface-container-low text-on-surface-variant">
              <tr>
                <th className="px-4 py-2 text-left font-medium">케이스 ID</th>
                <th className="px-4 py-2 text-left font-medium">검사일</th>
                <th className="px-4 py-2 text-left font-medium">상태</th>
                <th className="px-4 py-2 text-right font-medium">이미지</th>
                <th className="px-4 py-2 text-right font-medium">결함</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((c) => (
                <tr key={c.id} className="border-t border-outline-variant hover:bg-surface-container-low">
                  <td className="px-4 py-2">
                    <Link
                      to={`/cases/${c.case_id}`}
                      className="font-mono text-[12px] font-medium text-primary hover:underline"
                    >
                      {c.case_id}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-on-surface-variant">
                    {new Date(c.inspected_at).toLocaleDateString("ko-KR")}
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">
                    {c.total_images}
                  </td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">
                    {c.defect_count > 0 ? (
                      <span className="text-error">{c.defect_count}</span>
                    ) : (
                      <span className="text-on-surface-variant">0</span>
                    )}
                  </td>
                </tr>
              ))}
              {recent.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-on-surface-variant">
                    {err ? "—" : "불러오는 중..."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Kpi({
  label,
  value,
  icon,
  accent = "text-primary",
}: {
  label: string;
  value: number | undefined;
  icon: string;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4 shadow-card">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-on-surface-variant">{label}</span>
        <Icon name={icon} size={18} className={accent} />
      </div>
      <div className="mt-2 text-2xl font-bold tabular-nums text-on-surface">
        {value == null ? "—" : value.toLocaleString()}
      </div>
    </div>
  );
}
