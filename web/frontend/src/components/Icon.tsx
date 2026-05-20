// Material Symbols Outlined 아이콘 래퍼.
export default function Icon({
  name,
  className = "",
  size = 20,
}: {
  name: string;
  className?: string;
  size?: number;
}) {
  return (
    <span
      className={`material-symbols-outlined ${className}`}
      style={{ fontSize: `${size}px` }}
    >
      {name}
    </span>
  );
}
