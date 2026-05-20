// 상태/결함 표시용 작은 라벨 컴포넌트.
const STYLES: Record<string, string> = {
  READY: "bg-surface-container-high text-on-surface-variant",
  RUNNING: "bg-secondary-container text-on-secondary-container",
  COMPLETED: "bg-emerald-100 text-emerald-800",
  FAILED: "bg-error-container text-on-error-container",
  DEFECT: "bg-error-container text-on-error-container",
  NORMAL: "bg-emerald-100 text-emerald-800",
  EXAMPLE: "bg-surface-container-high text-on-surface-variant",
};

export default function StatusBadge({
  status,
  className = "",
}: {
  status: keyof typeof STYLES | string;
  className?: string;
}) {
  const cls = STYLES[status] ?? "bg-surface-container-high text-on-surface-variant";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${cls} ${className}`}
    >
      {status}
    </span>
  );
}
