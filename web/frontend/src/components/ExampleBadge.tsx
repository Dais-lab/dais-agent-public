// 실데이터가 없는 UI 영역에 부착하는 "예시" 회색 뱃지.
// CLAUDE.md "예시 처리 규칙" 참고.
export default function ExampleBadge({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-md bg-surface-container-high px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-on-surface-variant ${className}`}
      title="실데이터 미연동 — 추후 구현 예정"
    >
      예시
    </span>
  );
}
