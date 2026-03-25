export interface RunRow {
  run_id: string;
  topic: string;
  status: string;
  started_at?: string;
}

function statusLabel(status: string): string {
  switch (status) {
    case "completed":
      return "已完成";
    case "running":
      return "运行中";
    case "failed":
      return "失败";
    case "cancelled":
      return "已停止";
    default:
      return status;
  }
}

export function HistoryPanel({
  runs,
  onSelect,
  onDelete,
  loading,
  error,
}: {
  runs: RunRow[];
  onSelect: (runId: string) => void;
  onDelete: (runId: string) => void;
  loading: boolean;
  error: string | null;
}) {
  return (
    <section className="history-panel" aria-label="历史运行">
      <h3 className="history-panel__title">历史</h3>
      {error ? <p className="history-panel__warn">{error}</p> : null}
      {loading ? <p className="history-panel__muted">加载中…</p> : null}
      {!loading && runs.length === 0 ? (
        <p className="history-panel__muted">暂无记录</p>
      ) : null}
      <ul className="history-panel__list">
        {runs.map((r) => (
          <li key={r.run_id} className="history-panel__li">
            <button
              type="button"
              className="history-panel__item"
              onClick={() => onSelect(r.run_id)}
            >
              <span className="history-panel__topic">{r.topic}</span>
              <span className="history-panel__meta">
                <span className={`history-panel__st history-panel__st--${r.status}`}>
                  {statusLabel(r.status)}
                </span>
              </span>
            </button>
            {r.status === "completed" && (
              <span className="history-panel__export-hint" aria-hidden>↓</span>
            )}
            <button
              type="button"
              className="history-panel__del"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(r.run_id);
              }}
              title="删除此记录"
              aria-label={`删除 ${r.topic}`}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
