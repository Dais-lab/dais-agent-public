import Icon from "./Icon";

export default function Header() {
  return (
    <header className="flex h-14 items-center justify-between border-b border-outline-variant bg-surface-container-lowest px-6">
      <div className="relative flex-1 max-w-md">
        <Icon
          name="search"
          size={18}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant"
        />
        <input
          type="text"
          placeholder="케이스 / 모델 / 로그 검색..."
          disabled
          className="w-full rounded-lg border border-outline-variant bg-surface-container-low py-2 pl-10 pr-3 text-sm text-on-surface placeholder:text-on-surface-variant/70 focus:border-primary focus:outline-none disabled:opacity-60"
        />
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="grid h-9 w-9 place-items-center rounded-lg text-on-surface-variant hover:bg-surface-container"
          title="알림"
        >
          <Icon name="notifications" size={20} />
        </button>
        <button
          type="button"
          className="grid h-9 w-9 place-items-center rounded-lg text-on-surface-variant hover:bg-surface-container"
          title="설정"
        >
          <Icon name="settings" size={20} />
        </button>
        <div className="ml-2 grid h-9 w-9 place-items-center rounded-full bg-primary text-on-primary text-sm font-semibold">
          D
        </div>
      </div>
    </header>
  );
}
