import { NavLink } from "react-router-dom";
import Icon from "./Icon";

const NAV = [
  { to: "/", icon: "dashboard", label: "대시보드" },
  { to: "/cases", icon: "image_search", label: "결함 탐지" },
  { to: "/models", icon: "deployed_code", label: "모델 관리" },
  { to: "/monitoring", icon: "monitoring", label: "모니터링" },
];

export default function Sidebar() {
  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-outline-variant bg-surface-container-low">
      <div className="flex items-center gap-2 px-6 py-5">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-primary text-on-primary">
          <Icon name="hub" size={20} />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-bold tracking-tight text-on-surface">DaiS-Agent</span>
          <span className="text-[11px] font-medium text-on-surface-variant">MLOps Console</span>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1 px-3">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-primary text-on-primary"
                  : "text-on-surface-variant hover:bg-surface-container"
              }`
            }
          >
            <Icon name={item.icon} size={20} />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto border-t border-outline-variant px-4 py-3 text-[11px] leading-relaxed text-on-surface-variant">
        <div>v0.1.0 · Phase 5</div>
        <div className="mt-1 text-on-surface-variant/70">
          비전 AI 결함탐지 플랫폼
        </div>
      </div>
    </aside>
  );
}
