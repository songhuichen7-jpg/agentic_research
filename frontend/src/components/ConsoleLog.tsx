import { useEffect, useRef, useState } from "react";
import type { PipelineEvent } from "../state/pipelineReducer";

const phaseClass: Record<string, string> = {
  start: "console-line--start",
  end: "console-line--end",
  error: "console-line--err",
  cancelled: "console-line--cancelled",
  detail: "console-line--detail",
};

export function ConsoleLog({ events }: { events: PipelineEvent[] }) {
  const [expanded, setExpanded] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (expanded) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [events.length, expanded]);

  if (events.length === 0) return null;

  return (
    <div className="console-toggle">
      <button
        type="button"
        className="console-toggle__btn"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? "收起日志" : "查看详细日志"} ({events.length})
        <span className="console-toggle__arrow">{expanded ? "▲" : "▼"}</span>
      </button>
      {expanded && (
        <div className="console">
          <div className="console__body">
            {events.map((ev) => (
              <div
                key={`${ev.seq}-${ev.ts}`}
                className={`console-line ${phaseClass[ev.phase] ?? ""}`}
              >
                <span className="console-line__seq">#{ev.seq}</span>
                <span className="console-line__node">{ev.node}</span>
                <span className="console-line__phase">{ev.phase.toUpperCase()}</span>
                <span className="console-line__title">{ev.title}</span>
                {ev.detail && (
                  <span className="console-line__detail">{ev.detail}</span>
                )}
                {ev.error && (
                  <span className="console-line__error">{ev.error}</span>
                )}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </div>
      )}
    </div>
  );
}
