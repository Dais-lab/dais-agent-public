import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type {
  CaseSummary,
  ImagePage,
  PredictionRead,
  RunRead,
} from "../api/types";
import ChatPanel from "../components/ChatPanel";
import Icon from "../components/Icon";
import StatusBadge from "../components/StatusBadge";

export default function CaseList() {
  const { caseId: caseIdParam } = useParams();
  const nav = useNavigate();
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .cases({ limit: 200, sort: "asc" })
      .then((cs) => {
        setCases(cs);
        if (!caseIdParam && cs.length > 0) {
          // 가장 최근(오름차순 정렬 시 마지막) 케이스를 기본 선택
          const last = cs[cs.length - 1];
          nav(`/cases/${last.case_id}`, { replace: true });
        }
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selected = useMemo(
    () => cases.find((c) => c.case_id === caseIdParam) ?? null,
    [cases, caseIdParam],
  );

  // 결함 탐지 완료 후 사이드바 카운트/상태가 즉시 반영되도록 해당 case 1건만 재조회.
  const refreshCase = async (caseId: string) => {
    try {
      const fresh = await api.case(caseId);
      setCases((prev) => prev.map((c) => (c.case_id === caseId ? fresh : c)));
    } catch {
      // 실패해도 다른 기능 영향 없음 — 다음 새로고침 때 자연스럽게 동기화됨
    }
  };

  return (
    <div className="flex h-full">
      <CaseSidebar cases={cases} selected={selected} loading={loading} err={err} />
      <div className="flex flex-1 flex-col overflow-hidden">
        {selected ? (
          <CaseDetail
            caseSummary={selected}
            key={selected.case_id}
            onCaseUpdated={refreshCase}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center text-on-surface-variant">
            {loading ? "케이스 불러오는 중..." : "케이스를 선택하세요"}
          </div>
        )}
      </div>
      <ChatPanel />
    </div>
  );
}

// ──────────────────────────────────────────────
// 좌측: 케이스 목록
// ──────────────────────────────────────────────
function CaseSidebar({
  cases,
  selected,
  loading,
  err,
}: {
  cases: CaseSummary[];
  selected: CaseSummary | null;
  loading: boolean;
  err: string | null;
}) {
  const nav = useNavigate();
  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-outline-variant bg-surface-container-low">
      <div className="border-b border-outline-variant px-4 py-3">
        <h2 className="text-sm font-semibold text-on-surface">케이스 목록</h2>
        <p className="mt-0.5 text-[11px] text-on-surface-variant">
          {loading ? "..." : `${cases.length}개 · 날짜 내림차순`}
        </p>
      </div>
      <ul className="flex-1 overflow-auto">
        {err && <li className="px-4 py-3 text-xs text-error">{err}</li>}
        {cases.map((c) => {
          const isActive = selected?.case_id === c.case_id;
          return (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => nav(`/cases/${c.case_id}`)}
                className={`flex w-full items-center justify-between gap-2 border-l-2 px-4 py-3 text-left transition-colors ${
                  isActive
                    ? "border-primary bg-surface-container"
                    : "border-transparent hover:bg-surface-container"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate font-mono text-[12px] font-medium text-on-surface">
                    {c.case_id}
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-[11px] text-on-surface-variant">
                    <span>{new Date(c.inspected_at).toLocaleDateString("ko-KR")}</span>
                    <span>·</span>
                    <span className="tabular-nums">{c.total_images}장</span>
                    {c.defect_count > 0 && (
                      <span className="font-medium text-error">결함 {c.defect_count}</span>
                    )}
                  </div>
                </div>
                <StatusBadge status={c.status} className="shrink-0" />
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}

// ──────────────────────────────────────────────
// 우측: 케이스 상세 + 이미지 그리드 + 결함 탐지 버튼
// ──────────────────────────────────────────────
function CaseDetail({
  caseSummary,
  onCaseUpdated,
}: {
  caseSummary: CaseSummary;
  onCaseUpdated?: (caseId: string) => void;
}) {
  const [page, setPage] = useState(1);
  const [imagePage, setImagePage] = useState<ImagePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [run, setRun] = useState<RunRead | null>(null);
  const [predicting, setPredicting] = useState(false);
  const pollRef = useRef<number | null>(null);
  const [selectedImageId, setSelectedImageId] = useState<string | null>(null);

  const selectedIndex = useMemo(() => {
    if (!selectedImageId || !imagePage) return -1;
    return imagePage.items.findIndex((i) => i.id === selectedImageId);
  }, [selectedImageId, imagePage]);

  const goPrev = () => {
    if (!imagePage || selectedIndex <= 0) return;
    setSelectedImageId(imagePage.items[selectedIndex - 1].id);
  };
  const goNext = () => {
    if (!imagePage || selectedIndex < 0) return;
    if (selectedIndex >= imagePage.items.length - 1) return;
    setSelectedImageId(imagePage.items[selectedIndex + 1].id);
  };

  useEffect(() => {
    setLoading(true);
    api
      .images(caseSummary.case_id, page, 10)
      .then(setImagePage)
      .finally(() => setLoading(false));
  }, [caseSummary.case_id, page]);

  // case 가 바뀌면 page/run 초기화 + 최신 run 자동 로드 (새로고침 후 라벨 복원)
  useEffect(() => {
    setPage(1);
    setRun(null);
    setSelectedImageId(null);
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    let cancelled = false;
    api
      .latestRun(caseSummary.case_id)
      .then((latest) => {
        if (cancelled) return;
        if (latest) setRun(latest);
      })
      .catch(() => {
        // 최신 run 조회 실패는 무시 (라벨만 못 띄울 뿐 다른 기능 영향 없음)
      });
    return () => {
      cancelled = true;
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
      }
    };
  }, [caseSummary.case_id]);

  const predictionMap = useMemo(() => {
    const m = new Map<string, PredictionRead>();
    run?.predictions.forEach((p) => m.set(p.image_id, p));
    return m;
  }, [run]);

  function startPredict() {
    setPredicting(true);
    setRun(null);
    api
      .predict(caseSummary.case_id)
      .then((r) => {
        // 2초 polling
        pollRef.current = window.setInterval(async () => {
          const fresh = await api.run(caseSummary.case_id, r.run_id);
          setRun(fresh);
          if (fresh.status === "COMPLETED" || fresh.status === "FAILED") {
            if (pollRef.current) {
              window.clearInterval(pollRef.current);
              pollRef.current = null;
            }
            setPredicting(false);
            // 사이드바 카운트/상태 즉시 반영
            onCaseUpdated?.(caseSummary.case_id);
          }
        }, 2000);
      })
      .catch((e) => {
        setPredicting(false);
        alert(`결함 탐지 실행 실패: ${e}`);
      });
  }

  const total = imagePage?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / 10));

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* 헤더 */}
      <div className="flex items-center justify-between border-b border-outline-variant bg-surface-container-lowest px-6 py-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="font-mono text-lg font-bold text-on-surface">
              {caseSummary.case_id}
            </h2>
            <StatusBadge status={run?.status ?? caseSummary.status} />
          </div>
          <p className="mt-0.5 text-xs text-on-surface-variant">
            검사일 {new Date(caseSummary.inspected_at).toLocaleDateString("ko-KR")} · 이미지{" "}
            {caseSummary.total_images}장
            {caseSummary.defect_count > 0 && (
              <>
                {" "}· <span className="font-medium text-error">결함 {caseSummary.defect_count}</span>
              </>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={startPredict}
          disabled={predicting}
          className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-on-primary shadow-card hover:bg-primary-container disabled:cursor-not-allowed disabled:opacity-60"
        >
          {predicting ? (
            <>
              <Icon name="progress_activity" size={18} className="animate-spin" />
              탐지 중...
            </>
          ) : (
            <>
              <Icon name="bolt" size={18} />
              결함 탐지 실행
            </>
          )}
        </button>
      </div>

      {run && (
        <div
          className={`border-b border-outline-variant px-6 py-2 text-xs ${
            run.status === "FAILED"
              ? "bg-error-container text-on-error-container"
              : "bg-surface-container-low text-on-surface-variant"
          }`}
        >
          run <span className="font-mono">{run.id.slice(0, 8)}…</span> · status <b>{run.status}</b>
          {run.error_message && <> · {run.error_message}</>}
        </div>
      )}

      {/* 본문: 이미지 그리드 또는 상세 뷰 */}
      {selectedImageId ? (
        <ImageDetail
          imageId={selectedImageId!}
          filename={imagePage?.items.find((i) => i.id === selectedImageId)?.filename ?? ""}
          originalUrl={
            imagePage?.items.find((i) => i.id === selectedImageId)?.original_url ?? ""
          }
          prediction={predictionMap.get(selectedImageId)}
          onBack={() => setSelectedImageId(null)}
          onPrev={selectedIndex > 0 ? goPrev : undefined}
          onNext={
            imagePage && selectedIndex >= 0 && selectedIndex < imagePage.items.length - 1
              ? goNext
              : undefined
          }
          position={
            selectedIndex >= 0 && imagePage
              ? { current: selectedIndex + 1, total: imagePage.items.length }
              : undefined
          }
        />
      ) : (
        <>
          <div className="flex-1 overflow-auto p-6">
            {loading && !imagePage && (
              <div className="text-center text-on-surface-variant">이미지 불러오는 중...</div>
            )}
            {imagePage && imagePage.items.length === 0 && (
              <div className="text-center text-on-surface-variant">이미지 없음</div>
            )}
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
              {imagePage?.items.map((img) => {
                const pred = predictionMap.get(img.id);
                const borderCls = pred
                  ? pred.is_defect
                    ? "border-error ring-2 ring-error/30"
                    : "border-emerald-500 ring-2 ring-emerald-500/30"
                  : "border-outline-variant hover:border-primary";
                return (
                  <button
                    key={img.id}
                    type="button"
                    onClick={() => setSelectedImageId(img.id)}
                    className={`group relative overflow-hidden rounded-xl border bg-surface-container-lowest text-left transition-all ${borderCls}`}
                  >
                    <div className="aspect-square w-full bg-surface-container">
                      <img
                        src={img.original_url}
                        alt={img.filename}
                        loading="lazy"
                        className="h-full w-full object-cover"
                      />
                    </div>
                    <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/70 to-transparent px-2 py-1.5 text-[11px] text-white">
                      <span className="truncate font-mono">{img.filename.slice(0, 20)}…</span>
                      {pred && (
                        <span className="rounded bg-white/20 px-1.5 py-0.5 font-mono tabular-nums">
                          {pred.anomaly_score.toFixed(2)}
                        </span>
                      )}
                    </div>
                    {pred?.is_defect && (
                      <div className="absolute left-2 top-2 rounded-md bg-error px-1.5 py-0.5 text-[10px] font-bold text-white">
                        DEFECT
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 페이지네이션 */}
          <div className="flex items-center justify-between border-t border-outline-variant bg-surface-container-lowest px-6 py-3 text-sm">
            <span className="text-on-surface-variant">
              {total > 0 && (
                <>
                  {(page - 1) * 10 + 1}–{Math.min(page * 10, total)} / {total}장
                </>
              )}
            </span>
            <div className="flex items-center gap-1">
              <PagerBtn disabled={page <= 1} onClick={() => setPage(page - 1)}>
                <Icon name="chevron_left" size={18} />
              </PagerBtn>
              <span className="px-3 font-mono tabular-nums text-on-surface-variant">
                {page} / {totalPages}
              </span>
              <PagerBtn disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
                <Icon name="chevron_right" size={18} />
              </PagerBtn>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function PagerBtn({
  children,
  disabled,
  onClick,
}: {
  children: React.ReactNode;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="grid h-8 w-8 place-items-center rounded-md text-on-surface-variant hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-30"
    >
      {children}
    </button>
  );
}

// 이미지 상세 — 그리드 자리에 인라인으로 표시. 원본 위 / Annotation 아래.
function ImageDetail({
  imageId,
  filename,
  originalUrl,
  prediction,
  onBack,
  onPrev,
  onNext,
  position,
}: {
  imageId: string;
  filename: string;
  originalUrl: string;
  prediction?: PredictionRead;
  onBack: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  position?: { current: number; total: number };
}) {
  const [annoUrl, setAnnoUrl] = useState<string | null>(null);
  const [annoErr, setAnnoErr] = useState<string | null>(null);

  useEffect(() => {
    setAnnoUrl(null);
    setAnnoErr(null);
    api
      .imageUrl(imageId, "annotation")
      .then((r) => setAnnoUrl(r.url))
      .catch((e) => setAnnoErr(String(e)));
  }, [imageId]);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* 상세 헤더 — 뒤로 / prev / next / 메타 */}
      <div className="flex items-center justify-between border-b border-outline-variant bg-surface-container-lowest px-6 py-3">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onBack}
            title="그리드로"
            className="grid h-8 w-8 place-items-center rounded-md text-on-surface-variant hover:bg-surface-container"
          >
            <Icon name="arrow_back" size={18} />
          </button>
          <button
            type="button"
            onClick={onPrev}
            disabled={!onPrev}
            title="이전 이미지"
            className="grid h-8 w-8 place-items-center rounded-md text-on-surface-variant hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-30"
          >
            <Icon name="chevron_left" size={20} />
          </button>
          <button
            type="button"
            onClick={onNext}
            disabled={!onNext}
            title="다음 이미지"
            className="grid h-8 w-8 place-items-center rounded-md text-on-surface-variant hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-30"
          >
            <Icon name="chevron_right" size={20} />
          </button>
          {position && (
            <span className="ml-2 font-mono text-xs tabular-nums text-on-surface-variant">
              {position.current} / {position.total}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="font-mono text-on-surface-variant">{filename}</span>
          {prediction && (
            <>
              <span className="text-outline-variant">·</span>
              <span className="text-on-surface-variant">
                score{" "}
                <span className="font-mono font-semibold tabular-nums text-on-surface">
                  {prediction.anomaly_score.toFixed(4)}
                </span>
              </span>
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                  prediction.is_defect
                    ? "bg-error-container text-on-error-container"
                    : "bg-emerald-100 text-emerald-800"
                }`}
              >
                {prediction.is_defect ? "DEFECT" : "NORMAL"}
              </span>
            </>
          )}
        </div>
      </div>

      {/* 본문 — 원본(위) / Annotation(아래) 세로 스택 */}
      <div className="flex-1 space-y-4 overflow-auto bg-surface p-6">
        <ImagePanel title="원본" url={originalUrl} />
        <ImagePanel
          title="Annotation"
          url={annoUrl}
          error={annoErr}
          emptyHint="결함 탐지 실행 후 생성됩니다"
        />
      </div>
    </div>
  );
}

function ImagePanel({
  title,
  url,
  error,
  emptyHint,
}: {
  title: string;
  url: string | null | undefined;
  error?: string | null;
  emptyHint?: string;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-outline-variant bg-surface-container-lowest shadow-card">
      <header className="flex items-center justify-between border-b border-outline-variant px-4 py-2">
        <h3 className="text-sm font-semibold text-on-surface">{title}</h3>
      </header>
      <div className="grid place-items-center bg-surface-container p-4" style={{ minHeight: 320 }}>
        {error ? (
          <div className="text-center text-sm text-on-surface-variant">
            {emptyHint ?? error}
          </div>
        ) : !url ? (
          <div className="text-sm text-on-surface-variant">불러오는 중...</div>
        ) : (
          <img
            src={url}
            alt={title}
            className="max-h-[60vh] max-w-full rounded-md object-contain"
          />
        )}
      </div>
    </section>
  );
}
