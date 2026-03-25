import { useEffect, useState } from "react";

interface ArtifactsResponse {
  run_id: string;
  chart_count: number;
  charts: { filename: string; size_kb: number }[];
}

export function ResultPanel({
  runId,
  visible,
}: {
  runId: string | null;
  visible: boolean;
}) {
  const [art, setArt] = useState<ArtifactsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!runId || !visible) {
      setArt(null);
      setErr(null);
      return;
    }
    let cancelled = false;
    fetch(`/api/report/${encodeURIComponent(runId)}/artifacts`)
      .then((r) => {
        if (r.status === 404) return null;
        if (!r.ok) throw new Error(r.statusText);
        return r.json() as Promise<ArtifactsResponse>;
      })
      .then((data) => {
        if (!cancelled) setArt(data);
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, visible]);

  if (!runId || !visible) return null;

  const base = `/api/report/${encodeURIComponent(runId)}`;

  return (
    <section className="result-panel" aria-label="生成结果">
      <h3 className="result-panel__title">结果下载</h3>
      <div className="result-panel__links">
        <a className="result-panel__btn" href={`${base}/markdown`} download>
          Markdown
        </a>
        <a className="result-panel__btn" href={`${base}/pdf`} download>
          PDF
        </a>
      </div>
      {err ? <p className="result-panel__hint">图表列表暂不可用：{err}</p> : null}
      {art && art.chart_count > 0 ? (
        <div className="result-panel__charts">
          <p className="result-panel__hint">图表预览（{art.chart_count}）</p>
          <div className="result-panel__grid">
            {art.charts.map((c) => (
              <figure key={c.filename} className="result-panel__fig">
                <img
                  src={`${base}/charts/${encodeURIComponent(c.filename)}`}
                  alt={c.filename}
                  loading="lazy"
                />
                <figcaption>{c.filename}</figcaption>
              </figure>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
