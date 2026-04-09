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
  activeRunId,
}: {
  runs: RunRow[];
  onSelect: (runId: string) => void;
  onDelete: (runId: string) => void;
  loading: boolean;
  error: string | null;
  activeRunId: string | null;
}) {
  return (
    <nav className="sidebar__nav">
      {error && <p className="sidebar__error">{error}</p>}
      {loading && runs.length === 0 && (
        <p className="sidebar__muted">加载中…</p>
      )}
      {!loading && runs.length === 0 && (
        <p className="sidebar__muted">暂无记录</p>
      )}
      {runs.map((r) => (
        <div
          key={r.run_id}
          className={`sidebar__item ${r.run_id === activeRunId ? "sidebar__item--active" : ""}`}
        >
          <button
            type="button"
            className="sidebar__item-btn"
            onClick={() => onSelect(r.run_id)}
          >
            <span className="sidebar__item-topic">{r.topic}</span>
            <span
              className={`sidebar__item-status sidebar__item-status--${r.status}`}
            >
              {statusLabel(r.status)}
            </span>
          </button>
          <button
            type="button"
            className="sidebar__item-del"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(r.run_id);
            }}
            title="删除"
            aria-label={`删除 ${r.topic}`}
          >
            ×
          </button>
        </div>
      ))}
    </nav>
  );
}
