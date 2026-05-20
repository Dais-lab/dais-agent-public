import Icon from "../components/Icon";
import ExampleBadge from "../components/ExampleBadge";

const RESOURCES = [
  { name: "GPU 0 (A6000)", usage: 72, mem: "38 / 48 GB" },
  { name: "GPU 1 (A6000)", usage: 18, mem: "9 / 48 GB" },
  { name: "CPU", usage: 41, mem: "32 / 256 GB RAM" },
  { name: "Disk (/data)", usage: 64, mem: "1.2 / 2 TB" },
];

const LOGS = [
  { ts: "07:12:34", level: "INFO", msg: "Airflow DAG inference_pipeline finished (case=20260623_001)" },
  { ts: "07:11:09", level: "INFO", msg: "ml-inference /predict 200 in 1.84s" },
  { ts: "07:09:51", level: "WARN", msg: "MinIO health: latency 312ms (>250ms threshold)" },
  { ts: "07:07:23", level: "INFO", msg: "MLflow run dais_anomaly@v3.2 evaluated" },
];

export default function Monitoring() {
  return (
    <div className="space-y-6 p-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-on-surface">모니터링</h1>
          <p className="mt-1 text-sm text-on-surface-variant">
            인프라 리소스 / 시스템 로그 / 추론 큐 상태
          </p>
        </div>
        <div className="flex gap-2">
          <a
            href="http://203.250.72.36:8080"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-outline-variant bg-surface-container-lowest px-3 py-2 text-sm font-medium text-on-surface hover:border-primary"
          >
            <Icon name="open_in_new" size={16} />
            Airflow 열기
          </a>
          <a
            href="http://203.250.72.36:9090"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-outline-variant bg-surface-container-lowest px-3 py-2 text-sm font-medium text-on-surface hover:border-primary"
          >
            <Icon name="open_in_new" size={16} />
            Prometheus 열기
          </a>
        </div>
      </div>

      {/* 핵심 지표 */}
      <section className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Metric label="GPU 평균 사용률" value="45%" sub="2개 GPU 평균" />
        <Metric label="API 평균 응답시간" value="187ms" sub="ml-inference /predict" />
        <Metric label="대기 작업" value="3" sub="Airflow queued" />
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* 리소스 */}
        <section className="lg:col-span-2">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-on-surface-variant">
            인프라 리소스 <ExampleBadge />
          </h2>
          <div className="overflow-hidden rounded-xl border border-outline-variant bg-surface-container-lowest">
            <table className="w-full text-sm">
              <thead className="bg-surface-container-low text-on-surface-variant">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">리소스</th>
                  <th className="px-4 py-2 text-left font-medium">사용률</th>
                  <th className="px-4 py-2 text-right font-medium">메모리</th>
                </tr>
              </thead>
              <tbody>
                {RESOURCES.map((r) => (
                  <tr key={r.name} className="border-t border-outline-variant">
                    <td className="px-4 py-2 font-medium text-on-surface">{r.name}</td>
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-2">
                        <div className="h-2 w-32 overflow-hidden rounded-full bg-surface-container-high">
                          <div
                            className={`h-full ${
                              r.usage > 80
                                ? "bg-error"
                                : r.usage > 60
                                  ? "bg-amber-500"
                                  : "bg-primary"
                            }`}
                            style={{ width: `${r.usage}%` }}
                          />
                        </div>
                        <span className="font-mono text-xs tabular-nums">{r.usage}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-on-surface-variant">
                      {r.mem}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* 시스템 로그 */}
        <section>
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-on-surface-variant">
            실시간 시스템 로그 <ExampleBadge />
          </h2>
          <div className="space-y-2 rounded-xl border border-outline-variant bg-inverse-surface p-3 font-mono text-[11px] text-inverse-on-surface">
            {LOGS.map((l, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="shrink-0 text-on-surface-variant">{l.ts}</span>
                <span
                  className={`shrink-0 rounded px-1.5 ${
                    l.level === "WARN"
                      ? "bg-amber-500/30 text-amber-200"
                      : l.level === "ERROR"
                        ? "bg-error/40 text-red-200"
                        : "bg-emerald-500/20 text-emerald-200"
                  }`}
                >
                  {l.level}
                </span>
                <span className="break-all leading-relaxed">{l.msg}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4 shadow-card">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-on-surface-variant">{label}</span>
        <ExampleBadge />
      </div>
      <div className="mt-2 text-2xl font-bold tabular-nums text-on-surface">{value}</div>
      <div className="mt-0.5 text-[11px] text-on-surface-variant">{sub}</div>
    </div>
  );
}
