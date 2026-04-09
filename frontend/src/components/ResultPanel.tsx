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

  useEffect(() => {
    if (!runId || !visible) {
      setArt(null);
      return;
    }
    let cancelled = false;
    fetch(`/api/report/${encodeURIComponent(runId)}/artifacts`)
      .then((r) => {
        if (!r.ok) return null;
        return r.json() as Promise<ArtifactsResponse>;
      })
      .then((data) => {
        if (!cancelled) setArt(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [runId, visible]);

  if (!runId || !visible) return null;

  const base = `/api/report/${encodeURIComponent(runId)}`;

  return (
    <div className="result">
      <div className="result__header">研报已生成完成，可下载查看</div>
      <div className="result__actions">
        <a className="result__btn" href={`${base}/pdf`} download>
          下载 PDF
        </a>
        <a className="result__btn result__btn--secondary" href={`${base}/markdown`} download>
          下载 Markdown
        </a>
      </div>
      {art && art.chart_count > 0 && (
        <div className="result__charts">
          <div className="result__charts-label">图表预览 ({art.chart_count})</div>
          <div className="result__grid">
            {art.charts.map((c) => (
              <figure key={c.filename} className="result__fig">
                <img
                  src={`${base}/charts/${encodeURIComponent(c.filename)}`}
                  alt={c.filename}
                  loading="lazy"
                />
              </figure>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
