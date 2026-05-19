import Icon from "../components/Icon";
import ExampleBadge from "../components/ExampleBadge";

const MODEL_VERSIONS = [
  { ver: "v3.2", stage: "Production", date: "2026-05-10", acc: "94.8%", auroc: "0.972" },
  { ver: "v3.1", stage: "Staging", date: "2026-04-22", acc: "93.4%", auroc: "0.964" },
  { ver: "v3.0", stage: "Archived", date: "2026-03-30", acc: "91.2%", auroc: "0.953" },
];

export default function ModelManagement() {
  return (
    <div className="space-y-6 p-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-on-surface">모델 관리</h1>
          <p className="mt-1 text-sm text-on-surface-variant">
            MLflow Registry — DINOv3 anomaly detection 모델 버전 / 성능 추이
          </p>
        </div>
        <a
          href="http://203.250.72.36:5000"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-on-primary shadow-card hover:bg-primary-container"
        >
          <Icon name="open_in_new" size={18} />
          MLflow 열기
        </a>
      </div>

      {/* 현재 Production */}
      <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-card">
        <div className="flex items-center gap-2 text-sm font-semibold text-on-surface-variant">
          현재 Production 모델 <ExampleBadge />
        </div>
        <div className="mt-3 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Field label="모델명" value="dais_anomaly" mono />
          <Field label="버전" value="v3.2" mono />
          <Field label="배포일" value="2026-05-10" />
          <Field label="AUROC" value="0.972" accent="text-emerald-700" />
        </div>
      </section>

      {/* 모델 버전 테이블 */}
      <section>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-on-surface-variant">
          모델 버전 <ExampleBadge />
        </h2>
        <div className="overflow-hidden rounded-xl border border-outline-variant bg-surface-container-lowest">
          <table className="w-full text-sm">
            <thead className="bg-surface-container-low text-on-surface-variant">
              <tr>
                <th className="px-4 py-2 text-left font-medium">버전</th>
                <th className="px-4 py-2 text-left font-medium">단계</th>
                <th className="px-4 py-2 text-left font-medium">생성일</th>
                <th className="px-4 py-2 text-right font-medium">정확도</th>
                <th className="px-4 py-2 text-right font-medium">AUROC</th>
              </tr>
            </thead>
            <tbody>
              {MODEL_VERSIONS.map((m) => (
                <tr key={m.ver} className="border-t border-outline-variant">
                  <td className="px-4 py-2 font-mono font-medium">{m.ver}</td>
                  <td className="px-4 py-2">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                        m.stage === "Production"
                          ? "bg-primary/10 text-primary"
                          : m.stage === "Staging"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-surface-container-high text-on-surface-variant"
                      }`}
                    >
                      {m.stage}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-on-surface-variant">{m.date}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">{m.acc}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">{m.auroc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 성능 추이 차트 (예시) */}
      <section>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-on-surface-variant">
          성능 추이 <ExampleBadge />
        </h2>
        <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5">
          <div className="flex h-40 items-end gap-2">
            {[88, 89.5, 91.2, 92.1, 93.4, 94.8].map((v, i) => (
              <div key={i} className="flex flex-1 flex-col items-center gap-1">
                <div
                  className="w-full rounded-t bg-primary/60"
                  style={{ height: `${((v - 85) / 10) * 100}%` }}
                />
                <span className="font-mono text-[10px] text-on-surface-variant">v{i + 1}.0</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function Field({
  label,
  value,
  mono = false,
  accent = "text-on-surface",
}: {
  label: string;
  value: string;
  mono?: boolean;
  accent?: string;
}) {
  return (
    <div>
      <div className="text-[11px] font-medium uppercase tracking-wide text-on-surface-variant">
        {label}
      </div>
      <div className={`mt-1 text-sm font-semibold ${accent} ${mono ? "font-mono" : ""}`}>
        {value}
      </div>
    </div>
  );
}
