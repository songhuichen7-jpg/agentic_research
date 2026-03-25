import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { PipelineEvent } from "../state/pipelineReducer";

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleTimeString("zh-CN", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }) + "." + String(d.getMilliseconds()).padStart(3, "0");
  } catch {
    return iso;
  }
}

const phaseClass: Record<string, string> = {
  start: "console-line--start",
  end: "console-line--end",
  error: "console-line--err",
  cancelled: "console-line--cancelled",
  detail: "console-line--detail",
};

export function ConsoleLog({ events }: { events: PipelineEvent[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    if (!autoScroll) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length, autoScroll]);

  return (
    <section className="console" aria-label="详细事件日志">
      <header className="console__head">
        <h3 className="console__title">系统输出 · 全量事件</h3>
        <div className="console__tools">
          <label className="console__chk">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            自动滚动到底
          </label>
          <label className="console__chk">
            <input
              type="checkbox"
              checked={showRaw}
              onChange={(e) => setShowRaw(e.target.checked)}
            />
            显示原始 JSON
          </label>
        </div>
      </header>
      <div className="console__body">
        <AnimatePresence initial={false}>
          {events.map((ev) => (
            <motion.article
              key={`${ev.seq}-${ev.ts}`}
              className={`console-line ${phaseClass[ev.phase] ?? ""}`}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2 }}
            >
              <div className="console-line__row">
                <time className="console-line__time">{formatTime(ev.ts)}</time>
                <span className="console-line__seq">#{ev.seq}</span>
                <span className={`console-line__phase console-line__phase--${ev.phase}`}>
                  {ev.phase.toUpperCase()}
                </span>
                <span className="console-line__node">{ev.node}</span>
                <span className="console-line__actor">[{ev.actor}]</span>
              </div>
              <div className="console-line__title">{ev.title}</div>
              {ev.detail ? (
                <pre className="console-line__detail">{ev.detail}</pre>
              ) : null}
              {ev.error ? (
                <pre className="console-line__error">{ev.error}</pre>
              ) : null}
              {showRaw ? (
                <pre className="console-line__raw">{JSON.stringify(ev, null, 2)}</pre>
              ) : null}
            </motion.article>
          ))}
        </AnimatePresence>
        <div ref={bottomRef} />
      </div>
    </section>
  );
}
