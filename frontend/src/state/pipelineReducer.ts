/** SSE event shape — aligned with DEVELOPMENT_PLAN §7.2 */

export type Phase = "start" | "end" | "error" | "cancelled" | "detail";

export interface PipelineEvent {
  seq: number;
  ts: string;
  run_id: string;
  node: string;
  phase: Phase;
  actor: "system" | "agent";
  title: string;
  detail?: string;
  error?: string;
}

export type NodeStatus = "idle" | "running" | "done" | "error";

export interface NodeSlice {
  status: NodeStatus;
  title: string;
  detail?: string;
  error?: string;
  startedAt?: number;
  endedAt?: number;
}

export type PipelineStatus = "idle" | "running" | "done" | "error" | "cancelled" | "cancelling";

export interface PipelineState {
  nodes: Record<string, NodeSlice>;
  pipelineStatus: PipelineStatus;
  pipelineDetail?: string;
  pipelineError?: string;
  pipelineStartedAt?: number;
  log: PipelineEvent[];
}

/** System rail — pipeline order segment */
export const SYSTEM_NODE_IDS = [
  "collect_documents",
  "web_search",
  "build_evidence",
  "assemble",
  "quality_check",
  "export_pdf",
] as const;

/** Agent rail */
export const AGENT_NODE_IDS = ["plan", "write_sections", "charts"] as const;

export const ALL_NODE_IDS = [...SYSTEM_NODE_IDS, ...AGENT_NODE_IDS] as const;

/** LangGraph 实际执行顺序（与 `workflow` 边一致）— 用于流程图排布 */
export const PIPELINE_GRAPH_ORDER = [
  "collect_documents",
  "plan",
  "web_search",
  "build_evidence",
  "write_sections",
  "charts",
  "assemble",
  "quality_check",
  "export_pdf",
] as const;

const KNOWN_NODES = new Set<string>(ALL_NODE_IDS);

const DEFAULT_TITLE: Record<string, string> = {
  collect_documents: "采集研报与元数据",
  plan: "生成研究大纲与章节",
  web_search: "博查搜索补证据",
  build_evidence: "证据分块与向量入库",
  write_sections: "分章写作与引用",
  charts: "图表规划与渲染",
  assemble: "组装 Markdown 报告",
  quality_check: "质量检查",
  export_pdf: "导出 PDF",
};

function emptyNodes(): Record<string, NodeSlice> {
  const o: Record<string, NodeSlice> = {};
  for (const id of ALL_NODE_IDS) {
    o[id] = { status: "idle", title: DEFAULT_TITLE[id] ?? id };
  }
  return o;
}

export function initialPipelineState(): PipelineState {
  return {
    nodes: emptyNodes(),
    pipelineStatus: "idle",
    log: [],
  }
}

export type PipelineAction =
  | { type: "reset" }
  | { type: "optimistic_cancel" }
  | { type: "event"; payload: PipelineEvent };

const LOG_MAX = 500;

export function pipelineReducer(state: PipelineState, action: PipelineAction): PipelineState {
  if (action.type === "reset") {
    return initialPipelineState();
  }

  if (action.type === "optimistic_cancel") {
    // Only apply if the pipeline is currently running — don't overwrite terminal states
    if (state.pipelineStatus !== "running") return state;
    return {
      ...state,
      pipelineStatus: "cancelling",
      pipelineDetail: "正在请求停止…",
    };
  }

  const ev = action.payload;
  const log = [...state.log, ev].slice(-LOG_MAX);

  if (ev.node === "pipeline") {
    let pipelineStatus = state.pipelineStatus;
    let pipelineDetail = state.pipelineDetail;
    let pipelineError = state.pipelineError;
    let nodes = state.nodes;
    if (ev.phase === "start") {
      pipelineStatus = "running";
      pipelineDetail = ev.detail;
      pipelineError = undefined;
      return {
        ...state,
        nodes: state.nodes,
        pipelineStatus,
        pipelineDetail,
        pipelineError,
        pipelineStartedAt: Date.now(),
        log,
      };
    } else if (ev.phase === "end") {
      pipelineStatus = "done";
      pipelineDetail = ev.detail;
    } else if (ev.phase === "error") {
      pipelineStatus = "error";
      pipelineError = ev.error ?? ev.title;
    } else if (ev.phase === "cancelled") {
      pipelineStatus = "cancelled";
      pipelineDetail = ev.detail;
      pipelineError = ev.error ?? ev.title;
      nodes = { ...state.nodes };
      for (const id of ALL_NODE_IDS) {
        if (nodes[id].status === "running") {
          nodes[id] = { ...nodes[id], status: "idle", detail: "已中断" };
        }
      }
    }
    return {
      ...state,
      nodes,
      pipelineStatus,
      pipelineDetail,
      pipelineError,
      log,
    };
  }

  if (!KNOWN_NODES.has(ev.node)) {
    return { ...state, log };
  }

  const id = ev.node;
  const prev = state.nodes[id];
  let status: NodeStatus = prev.status;
  let detail = prev.detail;
  let error = prev.error;
  const title = ev.title || prev.title;

  let startedAt = prev.startedAt;
  let endedAt = prev.endedAt;

  if (ev.phase === "start") {
    status = "running";
    detail = ev.detail;
    error = undefined;
    startedAt = Date.now();
    endedAt = undefined;
  } else if (ev.phase === "end") {
    status = "done";
    detail = ev.detail;
    endedAt = Date.now();
  } else if (ev.phase === "error") {
    status = "error";
    error = ev.error ?? ev.title;
    endedAt = Date.now();
  } else if (ev.phase === "detail") {
    detail = ev.detail || prev.detail;
  }

  return {
    ...state,
    nodes: {
      ...state.nodes,
      [id]: { status, title, detail, error, startedAt, endedAt },
    },
    log,
  };
}
