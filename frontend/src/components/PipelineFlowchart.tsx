import { useEffect, useState } from "react";
import {
  PIPELINE_GRAPH_ORDER,
  type PipelineState,
} from "../state/pipelineReducer";

function formatDuration(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  if (totalSec < 60) return `${totalSec}s`;
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}:${String(sec).padStart(2, "0")}`;
}

function ElapsedTimer({ startedAt }: { startedAt: number }) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);
  return <>{formatDuration(Date.now() - startedAt)}</>;
}

function StepIcon({ status }: { status: string }) {
  if (status === "done") {
    return (
      <div className="step__icon step__icon--done">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path
            d="M2.5 7.5L5.5 10.5L11.5 4.5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    );
  }
  if (status === "running") {
    return (
      <div className="step__icon step__icon--running">
        <div className="spinner" />
      </div>
    );
  }
  if (status === "error") {
    return <div className="step__icon step__icon--error">!</div>;
  }
  return <div className="step__icon step__icon--idle" />;
}

export function PipelineSteps({ pipeline }: { pipeline: PipelineState }) {
  const { pipelineStatus } = pipeline;

  if (pipelineStatus === "idle") return null;

  const doneCount = PIPELINE_GRAPH_ORDER.filter(
    (id) => pipeline.nodes[id]?.status === "done",
  ).length;

  return (
    <div className="steps">
      <div className="steps__header">
        {pipelineStatus === "running" && "正在生成研报，请稍候…"}
        {pipelineStatus === "cancelling" && "正在停止任务…"}
        {pipelineStatus === "done" && (
          <>研报生成完成{pipeline.pipelineDetail ? ` · ${pipeline.pipelineDetail}` : ""}</>
        )}
        {pipelineStatus === "error" && "生成过程中出现错误"}
        {pipelineStatus === "cancelled" && "任务已停止"}
      </div>

      <div className="steps__progress">
        <div
          className={`steps__progress-fill${pipelineStatus === "done" ? " steps__progress-fill--done" : ""}`}
          style={{
            width: `${pipelineStatus === "done" ? 100 : (doneCount / PIPELINE_GRAPH_ORDER.length) * 100}%`,
          }}
        />
      </div>

      {(pipelineStatus === "running" || pipelineStatus === "cancelling") && (
        <div className="steps__meta">
          <span>
            步骤 {doneCount}/{PIPELINE_GRAPH_ORDER.length}
          </span>
          {pipeline.pipelineStartedAt && (
            <span>
              · 已运行 <ElapsedTimer startedAt={pipeline.pipelineStartedAt} />
            </span>
          )}
        </div>
      )}

      <div className="steps__list">
        {PIPELINE_GRAPH_ORDER.map((id) => {
          const node = pipeline.nodes[id];
          return (
            <div key={id} className={`step step--${node.status}`}>
              <StepIcon status={node.status} />
              <div className="step__body">
                <span className="step__title">{node.title}</span>
                {node.detail && node.status !== "idle" && (
                  <span className="step__detail">{node.detail}</span>
                )}
              </div>
              {node.startedAt && (
                <span className="step__time">
                  {node.endedAt ? (
                    formatDuration(node.endedAt - node.startedAt)
                  ) : (
                    <ElapsedTimer startedAt={node.startedAt} />
                  )}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
