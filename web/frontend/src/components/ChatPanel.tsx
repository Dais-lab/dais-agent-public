// 챗봇 UI — 비활성, "예시" 라벨 (CLAUDE.md Section 2).
import Icon from "./Icon";
import ExampleBadge from "./ExampleBadge";

const MOCK_MESSAGES = [
  {
    role: "assistant" as const,
    text: "안녕하세요. 결함 탐지 보조 Agent 입니다. 현재 케이스에 대해 무엇이 궁금하신가요?",
  },
];

export default function ChatPanel() {
  return (
    <div className="flex h-full w-80 shrink-0 flex-col border-l border-outline-variant bg-surface-container-lowest">
      <div className="flex items-center justify-between border-b border-outline-variant px-4 py-3">
        <div className="flex items-center gap-2">
          <Icon name="forum" size={18} className="text-primary" />
          <h3 className="text-sm font-semibold text-on-surface">결함 탐지 Agent</h3>
        </div>
        <ExampleBadge />
      </div>

      <div className="flex-1 space-y-3 overflow-auto p-4">
        {MOCK_MESSAGES.map((m, i) => (
          <div
            key={i}
            className="rounded-lg bg-surface-container-low p-3 text-sm leading-relaxed text-on-surface-variant"
          >
            {m.text}
          </div>
        ))}
        <div className="rounded-lg border border-dashed border-outline-variant p-3 text-xs leading-relaxed text-on-surface-variant/80">
          이 패널은 데모 UI 입니다. 추후 Correction Agent 연결 시 실제 추론 결과 기반 질의응답이
          가능해집니다.
        </div>
      </div>

      <div className="border-t border-outline-variant p-3">
        <div className="relative">
          <input
            type="text"
            disabled
            placeholder="추후 연결 예정..."
            className="w-full rounded-lg border border-outline-variant bg-surface-container-low py-2 pl-3 pr-10 text-sm text-on-surface placeholder:text-on-surface-variant/70 disabled:cursor-not-allowed disabled:opacity-60"
          />
          <button
            type="button"
            disabled
            className="absolute right-1.5 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-md bg-primary/40 text-on-primary disabled:cursor-not-allowed"
          >
            <Icon name="send" size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
