import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import {
  initialPipelineState,
  pipelineReducer,
  type PipelineEvent,
  type PipelineState,
} from "../state/pipelineReducer";

export interface UseRunStreamResult {
  pipeline: PipelineState;
  streamError: string | null;
  clearStreamError: () => void;
  startRun: (topic: string) => Promise<string>;
  cancelRun: (runId: string) => Promise<{ stale?: boolean } | void>;
  connectStream: (runId: string) => void;
  disconnect: () => void;
  resetPipeline: () => void;
  /** If server says this run is not ``running`` but UI still shows running, reset + disconnect. */
  syncRunFromServer: (runId: string) => Promise<void>;
}

/** Called when the pipeline reaches a terminal state via SSE or cancel. */
export type OnTerminalCallback = (runId: string, status: "done" | "error" | "cancelled") => void;

function isPipelineTerminal(ev: PipelineEvent): boolean {
  return (
    ev.node === "pipeline" &&
    (ev.phase === "end" || ev.phase === "error" || ev.phase === "cancelled")
  );
}

function terminalStatusFromEvent(ev: PipelineEvent): "done" | "error" | "cancelled" {
  if (ev.phase === "end") return "done";
  if (ev.phase === "cancelled") return "cancelled";
  return "error";
}

/** After normal completion the server closes the HTTP connection; some browsers fire
 * `error` on EventSource *before* the final `message` is delivered — defer "disconnected"
 * until we know we did not receive a terminal pipeline event. */
const DISCONNECT_ERROR_MS = 900;

export function useRunStream(onTerminal?: OnTerminalCallback): UseRunStreamResult {
  const [pipeline, dispatch] = useReducer(pipelineReducer, undefined, initialPipelineState);
  const pipelineRef = useRef(pipeline);
  pipelineRef.current = pipeline;

  const onTerminalRef = useRef(onTerminal);
  onTerminalRef.current = onTerminal;

  const [streamError, setStreamError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const sawPipelineTerminalRef = useRef(false);
  const disconnectErrorTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const clearDisconnectErrorTimer = useCallback(() => {
    if (disconnectErrorTimerRef.current !== undefined) {
      clearTimeout(disconnectErrorTimerRef.current);
      disconnectErrorTimerRef.current = undefined;
    }
  }, []);

  const disconnect = useCallback(() => {
    clearDisconnectErrorTimer();
    const cur = esRef.current;
    esRef.current = null;
    cur?.close();
  }, [clearDisconnectErrorTimer]);

  const clearStreamError = useCallback(() => setStreamError(null), []);

  const resetPipeline = useCallback(() => {
    dispatch({ type: "reset" });
  }, []);

  const syncRunFromServer = useCallback(
    async (runId: string) => {
      try {
        const r = await fetch(`/api/report/${encodeURIComponent(runId)}`, { cache: "no-store" });
        if (!r.ok) return;
        const row = (await r.json()) as { status?: string };
        if (!row.status) return;

        const localStatus = pipelineRef.current.pipelineStatus;

        // Local UI still thinks pipeline is running or cancelling, but server says terminal.
        if (localStatus === "running" || localStatus === "cancelling") {
          if (row.status === "completed") {
            dispatch({ type: "reset" });
            disconnect();
            onTerminalRef.current?.(runId, "done");
          } else if (row.status === "failed") {
            dispatch({ type: "reset" });
            disconnect();
            onTerminalRef.current?.(runId, "error");
          } else if (row.status === "cancelled") {
            dispatch({ type: "reset" });
            disconnect();
            onTerminalRef.current?.(runId, "cancelled");
          }
        }
      } catch {
        /* ignore */
      }
    },
    [disconnect],
  );

  const connectStream = useCallback(
    (runId: string, retryCount = 0) => {
      disconnect();
      setStreamError(null);
      sawPipelineTerminalRef.current = false;
      dispatch({ type: "reset" });

      const url = `/api/report/${encodeURIComponent(runId)}/stream`;

      // Ensure React finishes rendering after the reset above
      const openSSE = () => {
        const es = new EventSource(url);
        esRef.current = es;

        es.onmessage = (e: MessageEvent<string>) => {
          try {
            const payload = JSON.parse(e.data) as PipelineEvent;
            dispatch({ type: "event", payload });
            if (isPipelineTerminal(payload)) {
              sawPipelineTerminalRef.current = true;
              clearDisconnectErrorTimer();
              if (esRef.current === es) {
                esRef.current = null;
              }
              es.close();
              const terminalStatus = terminalStatusFromEvent(payload);
              onTerminalRef.current?.(runId, terminalStatus);
            }
          } catch {
            /* ignore */
          }
        };

        es.onerror = () => {
          if (esRef.current !== es) return;

          if (es.readyState === EventSource.CLOSED && retryCount < 3) {
            esRef.current = null;
            const delay = 500 * (retryCount + 1);
            setTimeout(() => {
              connectStream(runId, retryCount + 1);
            }, delay);
            return;
          }

          if (es.readyState === EventSource.CONNECTING) return;

          clearDisconnectErrorTimer();
          disconnectErrorTimerRef.current = setTimeout(() => {
            disconnectErrorTimerRef.current = undefined;
            if (sawPipelineTerminalRef.current) return;
            if (esRef.current !== es) return;
            if (es.readyState === EventSource.CLOSED) {
              setStreamError("事件流已断开，请确认后端在运行。");
            }
          }, DISCONNECT_ERROR_MS);
        };
      };

      // Use requestAnimationFrame to ensure DOM is ready before SSE connects
      if (typeof requestAnimationFrame !== "undefined") {
        requestAnimationFrame(openSSE);
      } else {
        setTimeout(openSSE, 0);
      }
    },
    [clearDisconnectErrorTimer, disconnect],
  );

  const startRun = useCallback(
    async (topic: string) => {
      const res = await fetch("/api/report/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, max_reports: 8 }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || res.statusText);
      }
      const data = (await res.json()) as { run_id: string };
      connectStream(data.run_id);
      return data.run_id;
    },
    [connectStream],
  );

  const cancelRun = useCallback(
    async (runId: string) => {
      // 1. Optimistic UI update — immediately show "cancelling"
      dispatch({ type: "optimistic_cancel" });

      // 2. Call the server
      const res = await fetch(`/api/report/${encodeURIComponent(runId)}/cancel`, {
        method: "GET",
        cache: "no-store",
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || res.statusText);
      }
      const data = (await res.json()) as { stale?: boolean };

      // 3. Stale run: no live thread, server already reconciled → immediately terminal
      if (data.stale) {
        dispatch({ type: "reset" });
        disconnect();
        onTerminalRef.current?.(runId, "cancelled");
      }
      // Non-stale: SSE will deliver `pipeline cancelled` event → reducer handles it
      // and connectStream's onmessage will fire onTerminal.

      return data;
    },
    [disconnect],
  );

  useEffect(
    () => () => {
      clearDisconnectErrorTimer();
      disconnect();
    },
    [clearDisconnectErrorTimer, disconnect],
  );

  return {
    pipeline,
    streamError,
    clearStreamError,
    startRun,
    cancelRun,
    connectStream,
    disconnect,
    resetPipeline,
    syncRunFromServer,
  };
}
