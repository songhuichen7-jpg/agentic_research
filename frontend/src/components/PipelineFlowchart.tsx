import { Fragment, useMemo } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  PIPELINE_GRAPH_ORDER,
  type PipelineState,
} from "../state/pipelineReducer";

/** 每行节点数 — 之字形：偶数行从左到右，奇数行从右到左 */
const FLOW_COLS = 4;

function touchedNodesFromLog(log: PipelineState["log"]): Set<string> {
  const s = new Set<string>();
  for (const e of log) {
    s.add(e.node);
  }
  return s;
}

function chunkRows<T>(arr: readonly T[], cols: number): T[][] {
  const rows: T[][] = [];
  for (let i = 0; i < arr.length; i += cols) {
    rows.push(arr.slice(i, i + cols) as T[]);
  }
  return rows;
}

/** 行间竖向连接：上一行末尾接到下一行开头（Z 拐角） */
function RowBridge({ align, cols }: { align: "left" | "right"; cols: number }) {
  return (
    <div
      className="flowchart__z-bridge"
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
      }}
      aria-hidden
    >
      <div
        className="flowchart__z-bridge__cell"
        style={{ gridColumn: align === "right" ? cols : 1 }}
      >
        <div className="flowchart__z-bridge__track">
          <div className="flowchart__z-bridge__fill" />
        </div>
        <span className="flowchart__z-bridge__glyph">↓</span>
      </div>
    </div>
  );
}

function FlowConnectorH({
  prevDone,
  nextActive,
  rtl,
}: {
  prevDone: boolean;
  nextActive: boolean;
  rtl: boolean;
}) {
  const lit = prevDone || nextActive;
  return (
    <div
      className={`flowchart__connector-h ${rtl ? "flowchart__connector-h--rtl" : ""}`}
      aria-hidden
    >
      <div className="flowchart__connector-h__track">
        <motion.div
          className={`flowchart__connector-h__fill ${lit ? "flowchart__connector-h__fill--on" : ""}`}
          initial={false}
          animate={{ scaleX: lit ? 1 : 0.15 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          style={{ transformOrigin: rtl ? "right center" : "left center" }}
        />
      </div>
      <motion.span
        className="flowchart__connector-h__glyph"
        animate={nextActive ? { opacity: [0.5, 1, 0.5], x: rtl ? [0, -3, 0] : [0, 3, 0] } : { opacity: 0.45, x: 0 }}
        transition={
          nextActive ? { duration: 1.4, repeat: Infinity, ease: "easeInOut" } : { duration: 0.2 }
        }
      >
        {rtl ? "←" : "→"}
      </motion.span>
    </div>
  );
}

function FlowNodeCard({
  id,
  index,
  slice,
  touched,
}: {
  id: string;
  index: number;
  slice: NonNullable<PipelineState["nodes"][string]>;
  touched: boolean;
}) {
  const st = slice.status;
  return (
    <motion.div
      layout
      className={`flow-node flow-node--${st} ${!touched ? "flow-node--faint" : ""}`}
      initial={false}
      animate={{
        scale: st === "running" ? 1.04 : 1,
        y: st === "running" ? -2 : 0,
      }}
      transition={{ type: "spring", stiffness: 380, damping: 26 }}
    >
      <div className="flow-node__ring" />
      <span className="flow-node__step">{String(index + 1).padStart(2, "0")}</span>
      <div className="flow-node__body">
        <div className="flow-node__title">{slice.title}</div>
        <div className="flow-node__code">{id}</div>
        <div className="flow-node__badge" data-status={st}>
          {st === "idle" && (touched ? "待开始" : "未到达")}
          {st === "running" && "执行中"}
          {st === "done" && "已完成"}
          {st === "error" && "失败"}
        </div>
        {slice.detail ? (
          <motion.p
            className="flow-node__detail"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            transition={{ duration: 0.25 }}
          >
            {slice.detail}
          </motion.p>
        ) : null}
        {slice.error ? <p className="flow-node__err">{slice.error}</p> : null}
      </div>
      <AnimatePresence>
        {st === "running" ? (
          <motion.div
            className="flow-node__scan"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            aria-hidden
          />
        ) : null}
      </AnimatePresence>
    </motion.div>
  );
}

export function PipelineFlowchart({ pipeline }: { pipeline: PipelineState }) {
  const touched = useMemo(() => touchedNodesFromLog(pipeline.log), [pipeline.log]);
  const doneCount = useMemo(
    () => PIPELINE_GRAPH_ORDER.filter((id) => pipeline.nodes[id]?.status === "done").length,
    [pipeline.nodes],
  );

  const rows = useMemo(() => chunkRows(PIPELINE_GRAPH_ORDER, FLOW_COLS), []);

  return (
    <section className="flowchart" aria-label="流水线流程图">
      <div className="flowchart__pipeline-meta">
        <motion.div
          className={`flowchart__pipeline-pill flowchart__pipeline-pill--${pipeline.pipelineStatus}`}
          layout
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <span className="flowchart__pipeline-dot" data-s={pipeline.pipelineStatus} />
          <span className="flowchart__pipeline-label">总流水线</span>
           <span className="flowchart__pipeline-state">
            {pipeline.pipelineStatus === "idle" && "等待启动"}
            {pipeline.pipelineStatus === "running" && "运行中"}
            {pipeline.pipelineStatus === "cancelling" &&
              (pipeline.pipelineDetail || "正在停止…")}
            {pipeline.pipelineStatus === "done" && "正常结束"}
            {pipeline.pipelineStatus === "cancelled" &&
              (pipeline.pipelineDetail || "已停止")}
            {pipeline.pipelineStatus === "error" && `异常：${pipeline.pipelineError ?? ""}`}
          </span>
          {pipeline.pipelineDetail ? (
            <span className="flowchart__pipeline-detail">{pipeline.pipelineDetail}</span>
          ) : null}
        </motion.div>
        <div className="flowchart__progress-hint">
          步骤进度 <strong>{doneCount}</strong> / {PIPELINE_GRAPH_ORDER.length}
        </div>
      </div>

      <div className="flowchart__body">
        <div className="flowchart__z">
          {rows.map((rowIds, ri) => (
            <Fragment key={ri}>
              {ri > 0 ? (
                <RowBridge
                  align={(ri - 1) % 2 === 0 ? "right" : "left"}
                  cols={FLOW_COLS}
                />
              ) : null}
              <div
                className={`flowchart__z-row ${ri % 2 === 1 ? "flowchart__z-row--reverse" : ""} ${
                  rowIds.length < FLOW_COLS ? "flowchart__z-row--short" : ""
                }`}
              >
                {rowIds.map((id, j) => {
                  const gi = ri * FLOW_COLS + j;
                  const slice = pipeline.nodes[id];
                  const isTouched = touched.has(id);
                  const prevId = gi > 0 ? PIPELINE_GRAPH_ORDER[gi - 1] : null;
                  const prevDone = prevId
                    ? pipeline.nodes[prevId]?.status === "done"
                    : false;
                  return (
                    <Fragment key={id}>
                      {j > 0 ? (
                        <FlowConnectorH
                          prevDone={!!prevDone}
                          nextActive={slice.status === "running"}
                          rtl={ri % 2 === 1}
                        />
                      ) : null}
                      <FlowNodeCard id={id} index={gi} slice={slice} touched={isTouched} />
                    </Fragment>
                  );
                })}
              </div>
            </Fragment>
          ))}
        </div>
      </div>
    </section>
  );
}
