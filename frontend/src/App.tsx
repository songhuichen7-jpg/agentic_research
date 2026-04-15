import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CanvasPanel } from "./components/CanvasPanel";
import { ConsoleLog } from "./components/ConsoleLog";
import { PipelineSteps } from "./components/PipelineFlowchart";
import { HistoryPanel, type RunRow } from "./components/HistoryPanel";
import { useRunStream, type OnTerminalCallback } from "./hooks/useRunStream";

const SUGGESTIONS = ["低空经济", "人形机器人", "新能源汽车", "人工智能"];

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  intent?: "edit" | "research";
  summary?: string;
  loading?: boolean;
  version?: number;
}

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

let _msgId = 0;
function nextMsgId() {
  return `msg-${++_msgId}`;
}

export default function App() {
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const refreshHistory = useCallback(() => {
    setHistoryLoading(true);
    setHistoryError(null);
    fetchHistory()
      .then(setRuns)
      .catch(() => {
        setRuns([]);
        setHistoryError("无法加载历史记录");
      })
      .finally(() => setHistoryLoading(false));
  }, []);

  const onTerminal: OnTerminalCallback = useCallback(
    (_runId, status) => {
      refreshHistory();
      // Browser notification when tab is not visible
      if (document.visibilityState === "hidden" && status === "done") {
        if (Notification.permission === "granted") {
          new Notification("研报助手", { body: "研报已生成完成", icon: "/favicon.ico" });
        }
        // Flash tab title
        const original = document.title;
        let flash = true;
        const interval = setInterval(() => {
          document.title = flash ? "✓ 研报已完成" : original;
          flash = !flash;
        }, 1000);
        const stopFlash = () => {
          clearInterval(interval);
          document.title = original;
          document.removeEventListener("visibilitychange", stopFlash);
        };
        document.addEventListener("visibilitychange", stopFlash);
      }
    },
    [refreshHistory],
  );

  const {
    pipeline,
    cancelRun,
    connectStream,
    streamError,
    clearStreamError,
    syncRunFromServer,
    resetPipeline,
  } = useRunStream(onTerminal);

  const [topic, setTopic] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [cancelBusy, setCancelBusy] = useState(false);
  const [canvasOpen, setCanvasOpen] = useState(false);
  const [revisionMessages, setRevisionMessages] = useState<ChatMessage[]>([]);
  const [canvasVersion, setCanvasVersion] = useState(0);
  // undefined = show latest (no ?v= param), number = show specific version
  const [canvasViewVersion, setCanvasViewVersion] = useState<number | undefined>(undefined);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    refreshHistory();
  }, [refreshHistory]);

  useEffect(() => {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  useEffect(() => {
    const onVis = () => {
      if (document.visibilityState === "visible" && runId) {
        void syncRunFromServer(runId);
      }
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [runId, syncRunFromServer]);

  const currentRunMeta = useMemo(
    () => runs.find((r) => r.run_id === runId),
    [runs, runId],
  );
  const displayTopic = currentRunMeta?.topic || topic || "";

  const pipelineActive = pipeline.pipelineStatus !== "idle";

  const showStopButton =
    !!runId &&
    (currentRunMeta?.status === "running" ||
      pipeline.pipelineStatus === "running" ||
      pipeline.pipelineStatus === "cancelling");

  const showResult =
    !!runId &&
    (pipeline.pipelineStatus === "done" ||
      (currentRunMeta?.status === "completed" && !pipelineActive));

  // In revision mode: report is done and user can send follow-up messages
  const isRevisionMode = showResult;

  const onPickHistory = (id: string) => {
    setRunId(id);
    setFormError(null);
    setRevisionMessages([]);
    connectStream(id);
    setMobileMenuOpen(false);
  };

  const onSubmitNew = async (t: string) => {
    setFormError(null);
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
      setRunId(data.run_id);
      setRevisionMessages([]);
      connectStream(data.run_id);
      refreshHistory();
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setBusy(false);
    }
  };

  const onSubmitRevision = async (message: string) => {
    if (!runId) return;
    setFormError(null);
    setBusy(true);

    const userMsg: ChatMessage = { id: nextMsgId(), role: "user", content: message };
    const loadingMsg: ChatMessage = {
      id: nextMsgId(),
      role: "assistant",
      content: "正在修改研报…",
      loading: true,
    };
    setRevisionMessages((prev) => [...prev, userMsg, loadingMsg]);

    try {
      const res = await fetch(`/api/report/${encodeURIComponent(runId)}/revise`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, topic: displayTopic }),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || res.statusText);
      }
      const data = (await res.json()) as {
        intent: string;
        summary: string;
        old_version: number;
        new_version: number;
      };

      setRevisionMessages((prev) =>
        prev.map((m) =>
          m.id === loadingMsg.id
            ? {
                ...m,
                content: data.summary || "修改完成",
                summary: data.summary,
                loading: false,
                intent: data.intent as "edit" | "research",
                version: data.old_version,
              }
            : m,
        ),
      );
      setCanvasVersion((v) => v + 1);
      setCanvasViewVersion(undefined); // show latest
      setCanvasOpen(true);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : "修改失败";
      setRevisionMessages((prev) =>
        prev.map((m) =>
          m.id === loadingMsg.id
            ? { ...m, content: `修改失败：${errMsg}`, loading: false }
            : m,
        ),
      );
      setFormError(errMsg);
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const t = topic.trim();
    if (!t) {
      setFormError(isRevisionMode ? "请输入修改要求" : "请输入行业主题");
      return;
    }
    setTopic("");
    if (isRevisionMode) {
      await onSubmitRevision(t);
    } else {
      await onSubmitNew(t);
    }
  };

  const onDeleteRun = async (id: string) => {
    try {
      await fetch(`/api/runs/${encodeURIComponent(id)}`, { method: "DELETE" });
      setRuns((prev) => prev.filter((r) => r.run_id !== id));
      if (runId === id) {
        setRunId(null);
        resetPipeline();
        setRevisionMessages([]);
      }
    } catch {
      /* ignore */
    }
  };

  const onCancelRun = async () => {
    if (!runId || cancelBusy) return;
    setCancelBusy(true);
    try {
      await cancelRun(runId);
    } catch {
      /* ignore */
    } finally {
      setCancelBusy(false);
    }
  };

  const handleNew = useCallback(() => {
    setRunId(null);
    resetPipeline();
    setTopic("");
    setFormError(null);
    setCanvasOpen(false);
    setRevisionMessages([]);
    setCanvasViewVersion(undefined);
    setMobileMenuOpen(false);
  }, [resetPipeline]);

  const handleSuggestion = (s: string) => {
    setTopic(s);
  };

  // Auto-scroll chat to bottom on new events
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [pipeline.log.length, runId, revisionMessages.length]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Cmd/Ctrl+N: new report
      if ((e.metaKey || e.ctrlKey) && e.key === 'n') {
        e.preventDefault();
        handleNew();
      }
      // Escape: close canvas or mobile menu
      if (e.key === 'Escape') {
        if (canvasOpen) setCanvasOpen(false);
        else if (mobileMenuOpen) setMobileMenuOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [canvasOpen, mobileMenuOpen, handleNew]);

  const avatarSvg = (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
      <path d="M14 2v6h6" />
    </svg>
  );

  return (
    <div className={`app${canvasOpen && runId ? " app--canvas" : ""}`}>
      {/* ── Sidebar ── */}
      <aside className={`sidebar${mobileMenuOpen ? " sidebar--mobile-open" : ""}`}>
        {mobileMenuOpen && <div className="sidebar__overlay" onClick={() => setMobileMenuOpen(false)} />}
        <div className="sidebar__header">
          <span className="sidebar__logo">
            <svg className="sidebar__logo-icon" width="20" height="20" viewBox="0 0 32 32" fill="none">
              <rect x="5" y="2" width="22" height="28" rx="3" fill="white" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M22 2v6a2 2 0 0 0 2 2h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              <path d="M10 16L13 13L16.5 17L19 14.5L22 18" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
              <line x1="10" y1="22" x2="22" y2="22" stroke="currentColor" opacity="0.3" strokeWidth="1.2" strokeLinecap="round"/>
              <line x1="10" y1="25" x2="18" y2="25" stroke="currentColor" opacity="0.2" strokeWidth="1.2" strokeLinecap="round"/>
            </svg>
            研报助手
          </span>
          <button type="button" className="sidebar__new" onClick={handleNew}>
            + 新建
          </button>
        </div>
        <HistoryPanel
          runs={runs}
          loading={historyLoading}
          error={historyError}
          onSelect={onPickHistory}
          onDelete={onDeleteRun}
          activeRunId={runId}
        />
      </aside>

      {/* ── Chat area ── */}
      <main className="chat">
        <button type="button" className="mobile-menu-btn" onClick={() => setMobileMenuOpen(true)} aria-label="菜单">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <line x1="3" y1="5" x2="17" y2="5" />
            <line x1="3" y1="10" x2="17" y2="10" />
            <line x1="3" y1="15" x2="17" y2="15" />
          </svg>
        </button>
        <div className="chat__scroll" ref={scrollRef}>
          {!runId ? (
            /* ── Welcome screen ── */
            <div className="chat__welcome">
              <div className="chat__welcome-icon">
                <svg width="30" height="30" viewBox="0 0 32 32" fill="none">
                  <rect x="5" y="2" width="22" height="28" rx="3" fill="white" stroke="var(--accent)" strokeWidth="1.5"/>
                  <path d="M22 2v6a2 2 0 0 0 2 2h3" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round"/>
                  <path d="M10 16L13 13L16.5 17L19 14.5L22 18" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                  <line x1="10" y1="22" x2="22" y2="22" stroke="var(--accent)" opacity="0.3" strokeWidth="1.2" strokeLinecap="round"/>
                  <line x1="10" y1="25" x2="18" y2="25" stroke="var(--accent)" opacity="0.2" strokeWidth="1.2" strokeLinecap="round"/>
                </svg>
              </div>
              <h1>行业研报助手</h1>
              <p>输入行业主题，自动采集数据、分析研究并生成专业研究报告</p>
              <div className="chat__suggestions">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="chat__suggestion"
                    onClick={() => handleSuggestion(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* ── Chat thread ── */
            <div className="chat__thread">
              {/* User initial message */}
              {displayTopic && (
                <div className="msg msg--user">
                  <div className="msg__bubble">
                    帮我生成一份「{displayTopic}」行业研报
                  </div>
                </div>
              )}

              {/* AI progress message — show placeholder while waiting for first SSE event */}
              {!!runId && !showResult && !pipelineActive && (
                <div className="msg msg--ai">
                  <div className="msg__avatar">{avatarSvg}</div>
                  <div className="msg__bubble">
                    <div className="revision-loading">
                      <div className="spinner" />
                      <span>正在启动研报生成…</span>
                    </div>
                  </div>
                </div>
              )}

              {/* AI progress message */}
              {pipelineActive && (
                <div className="msg msg--ai">
                  <div className="msg__avatar">{avatarSvg}</div>
                  <div className="msg__bubble">
                    <PipelineSteps pipeline={pipeline} />
                    {showStopButton && (
                      <button
                        type="button"
                        className="msg__stop"
                        onClick={onCancelRun}
                        disabled={cancelBusy}
                      >
                        {cancelBusy ||
                        pipeline.pipelineStatus === "cancelling"
                          ? "停止中…"
                          : "停止生成"}
                      </button>
                    )}
                    <ConsoleLog events={pipeline.log} />
                  </div>
                </div>
              )}

              {/* Result message */}
              {showResult && (
                <div className="msg msg--ai">
                  <div className="msg__avatar">{avatarSvg}</div>
                  <div className="msg__bubble">
                    <div className="result-card">
                      <div className="result-card__icon">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
                          <path d="M14 2v6h6" />
                          <path d="M16 13H8" />
                          <path d="M16 17H8" />
                          <path d="M10 9H8" />
                        </svg>
                      </div>
                      <div className="result-card__body">
                        <div className="result-card__title">
                          「{displayTopic}」行业研报
                        </div>
                        <div className="result-card__desc">
                          {revisionMessages.length > 0 ? "v1 · 初始版本" : "研报已生成完成"}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="result-card__open"
                        onClick={() => {
                          if (revisionMessages.length > 0) {
                            // Has revisions: show v1 (first backup)
                            setCanvasViewVersion(1);
                          } else {
                            // No revisions yet: show latest
                            setCanvasViewVersion(undefined);
                          }
                          setCanvasOpen(true);
                        }}
                      >
                        查看报告
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* ── Revision messages ── */}
              {revisionMessages.map((msg) =>
                msg.role === "user" ? (
                  <div key={msg.id} className="msg msg--user">
                    <div className="msg__bubble">{msg.content}</div>
                  </div>
                ) : (
                  <div key={msg.id} className="msg msg--ai">
                    <div className="msg__avatar">{avatarSvg}</div>
                    <div className="msg__bubble">
                      {msg.loading ? (
                        <div className="revision-loading">
                          <div className="spinner" />
                          <span>{msg.content}</span>
                        </div>
                      ) : (
                        <div className="revision-result">
                          {msg.intent && (
                            <span className={`revision-badge revision-badge--${msg.intent}`}>
                              {msg.intent === "research" ? "搜索+改写" : "直接改写"}
                            </span>
                          )}
                          {/* Change summary */}
                          <div className="revision-summary">
                            {msg.content.split("\n").map((line, i) => (
                              <div key={i} className="revision-summary__line">
                                {line}
                              </div>
                            ))}
                          </div>
                          {/* New version card — shows latest version at time of this revision */}
                          <div className="result-card">
                            <div className="result-card__icon">
                              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
                                <path d="M14 2v6h6" />
                                <path d="M16 13H8" />
                                <path d="M16 17H8" />
                                <path d="M10 9H8" />
                              </svg>
                            </div>
                            <div className="result-card__body">
                              <div className="result-card__title">
                                「{displayTopic}」行业研报
                              </div>
                              <div className="result-card__desc">
                                v{(msg.version ?? 0) + 1} · 已更新
                              </div>
                            </div>
                            <button
                              type="button"
                              className="result-card__open"
                              onClick={() => {
                                // Show the result of this revision.
                                // If a later revision exists, this version was backed up as v{N+1}.
                                // If this is the latest revision, show current file (undefined).
                                const assistantMsgs = revisionMessages.filter(m => m.role === "assistant" && !m.loading);
                                const isLast = assistantMsgs[assistantMsgs.length - 1]?.id === msg.id;
                                if (isLast) {
                                  setCanvasViewVersion(undefined);
                                } else {
                                  // This revision's output was backed up as v{old_version + 1}
                                  setCanvasViewVersion((msg.version ?? 0) + 1);
                                }
                                setCanvasOpen(true);
                              }}
                            >
                              查看报告
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ),
              )}
            </div>
          )}
        </div>

        {/* ── Input bar ── */}
        <div className="chat__bar">
          {(formError || streamError) && (
            <div className="chat__error-bar">
              <span>{formError || streamError}</span>
              <button
                type="button"
                className="chat__error-dismiss"
                onClick={() => {
                  setFormError(null);
                  if (streamError) clearStreamError();
                }}
              >
                ×
              </button>
            </div>
          )}
          <form className="chat__form" onSubmit={onSubmit}>
            <input
              className="chat__input"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder={
                isRevisionMode
                  ? "输入修改要求，如：第三章补充竞争格局分析…"
                  : "输入行业主题，如：低空经济、人形机器人…"
              }
              disabled={busy}
              autoComplete="off"
            />
            <button
              type="submit"
              className="chat__send"
              disabled={busy || !topic.trim()}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path
                  d="M10 16V4M10 4L5 9M10 4L15 9"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </form>
        </div>
      </main>

      {/* ── Canvas panel ── */}
      {canvasOpen && runId && (
        <CanvasPanel
          runId={runId}
          version={canvasViewVersion}
          key={`${runId}-${canvasVersion}-${canvasViewVersion ?? "latest"}`}
          onClose={() => setCanvasOpen(false)}
        />
      )}
    </div>
  );
}
