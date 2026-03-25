import { useCallback, useEffect, useMemo, useState } from "react";
import { ConsoleLog } from "./components/ConsoleLog";
import { PipelineFlowchart } from "./components/PipelineFlowchart";
import { HistoryPanel, type RunRow } from "./components/HistoryPanel";
import { ResultPanel } from "./components/ResultPanel";
import { useRunStream, type OnTerminalCallback } from "./hooks/useRunStream";

async function fetchHistory(): Promise<RunRow[]> {
  const r = await fetch("/api/runs?limit=50");
  if (!r.ok) throw new Error(r.statusText);
  const rows = (await r.json()) as Record<string, unknown>[];
  return rows
    .map((row) => ({
      run_id: String(row.run_id ?? ""),
      topic: String(row.topic ?? ""),
      status: String(row.status ?? ""),
      started_at: row.started_at != null ? String(row.started_at) : undefined,
    }))
    .filter((row) => row.status === "completed" || row.status === "running");
}

export default function App() {
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const refreshHistory = useCallback(() => {
    setHistoryLoading(true);
    setHistoryError(null);
    fetchHistory()
      .then((rows) => {
        setRuns(rows);
      })
      .catch(() => {
        setRuns([]);
        setHistoryError("无法加载历史列表（请确认后端已启动）。");
      })
      .finally(() => setHistoryLoading(false));
  }, []);

  // When pipeline reaches a terminal state (done / error / cancelled via SSE or cancel),
  // refresh the history list so the sidebar status stays in sync.
  const onTerminal: OnTerminalCallback = useCallback(
    (_runId, _status) => {
      refreshHistory();
    },
    [refreshHistory],
  );

  const {
    pipeline,
    startRun,
    cancelRun,
    connectStream,
    streamError,
    clearStreamError,
    syncRunFromServer,
    resetPipeline,
  } = useRunStream(onTerminal);
  const [topic, setTopic] = useState("低空经济");
  const [runId, setRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [cancelBusy, setCancelBusy] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  useEffect(() => {
    refreshHistory();
  }, [refreshHistory]);

  /** 切回标签时对照服务器：重启后 DB 已非 running 但本地仍显示「运行中」时纠偏 */
  useEffect(() => {
    const onVis = () => {
      if (document.visibilityState === "visible" && runId) {
        void syncRunFromServer(runId);
      }
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [runId, syncRunFromServer]);

  const currentRunMeta = useMemo(() => runs.find((r) => r.run_id === runId), [runs, runId]);
  const serverSaysRunning = currentRunMeta?.status === "running";
  const showStopButton =
    !!runId &&
    (serverSaysRunning ||
      pipeline.pipelineStatus === "running" ||
      pipeline.pipelineStatus === "cancelling");

  const onPickHistory = async (id: string) => {
    setRunId(id);
    setCancelError(null);
    // Connect SSE immediately — don't wait for the status check
    connectStream(id);
    // Check server status in background; reset pipeline if already finished
    fetch(`/api/report/${encodeURIComponent(id)}`, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) return;
        return r.json() as Promise<{ status?: string }>;
      })
      .then((row) => {
        if (row?.status && row.status !== "running") {
          resetPipeline();
        }
      })
      .catch(() => {});
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const t = topic.trim();
    if (!t) {
      setFormError("请输入行业主题");
      return;
    }
    setFormError(null);
    setCancelError(null);
    setBusy(true);
    try {
      const res = await fetch("/api/report/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: t, max_reports: 8 }),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || res.statusText);
      }
      const data = (await res.json()) as { run_id: string };
      // Use same flow as clicking a history item — reliable SSE + fresh pipeline
      onPickHistory(data.run_id);
      refreshHistory();
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setBusy(false);
    }
  };

  const onDeleteRun = async (id: string) => {
    try {
      await fetch(`/api/runs/${encodeURIComponent(id)}`, { method: "DELETE" });
      setRuns((prev) => prev.filter((r) => r.run_id !== id));
      if (runId === id) {
        setRunId(null);
        resetPipeline();
      }
    } catch {
      /* ignore */
    }
  };

  const terminal =
    pipeline.pipelineStatus === "done" ||
    pipeline.pipelineStatus === "error" ||
    pipeline.pipelineStatus === "cancelled";

  const onCancelRun = async () => {
    if (!runId || cancelBusy) return;
    setCancelBusy(true);
    setCancelError(null);
    try {
      await cancelRun(runId);
      // History refresh is handled by onTerminal callback when SSE delivers the cancelled event
    } catch (err: unknown) {
      setCancelError(err instanceof Error ? err.message : "停止失败");
    } finally {
      setCancelBusy(false);
    }
  };

  return (
    <div className="app app--studio">
      <header className="header">
        <div className="header__brand">
          <h1>行业研报 Agent</h1>
        </div>
        <form className="header__form" onSubmit={onSubmit}>
          <label className="header__label" htmlFor="topic-input">
            行业主题
          </label>
          <input
            id="topic-input"
            className="header__input"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="例如：人形机器人、低空经济"
            disabled={busy}
            autoComplete="off"
          />
          <button type="submit" className="header__submit" disabled={busy}>
            {busy ? "提交中…" : "开始生成"}
          </button>
        </form>
        {formError ? <p className="header__error">{formError}</p> : null}
        {cancelError ? <p className="header__error">{cancelError}</p> : null}
        {streamError ? (
          <div className="stream-banner" role="alert">
            <p className="stream-banner__text">{streamError}</p>
            <button type="button" className="stream-banner__dismiss" onClick={clearStreamError}>
              关闭
            </button>
          </div>
        ) : null}
        {showStopButton ? (
          <div className="header__run">
            <button
              type="button"
              className="header__cancel-run"
              onClick={onCancelRun}
              disabled={cancelBusy}
            >
              {cancelBusy || pipeline.pipelineStatus === "cancelling"
                ? "停止中…"
                : "停止任务"}
            </button>
          </div>
        ) : null}
      </header>

      <div className="studio">
        <main className="studio__main">
          <PipelineFlowchart key={runId ?? "idle"} pipeline={pipeline} />
          <ConsoleLog events={pipeline.log} />
          <ResultPanel runId={runId} visible={terminal && !!runId} />
        </main>
        <aside className="studio__aside">
          <HistoryPanel
            runs={runs}
            loading={historyLoading}
            error={historyError}
            onSelect={onPickHistory}
            onDelete={onDeleteRun}
          />
        </aside>
      </div>
    </div>
  );
}
