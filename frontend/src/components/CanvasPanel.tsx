import React, { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function CanvasPanel({
  runId,
  version,
  onClose,
}: {
  runId: string;
  version?: number;
  onClose: () => void;
}) {
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [headings, setHeadings] = useState<string[]>([]);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);

  const base = `/api/report/${encodeURIComponent(runId)}`;
  const mdUrl = version ? `${base}/markdown?v=${version}` : `${base}/markdown`;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(mdUrl, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error("无法加载报告");
        return r.text();
      })
      .then((md) => {
        if (!cancelled) {
          setMarkdown(md);
          setHeadings((md.match(/^## .+$/gm) || []).map(h => h.replace('## ', '')));
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [runId, mdUrl]);

  // Map local chart image paths in markdown to API URLs
  const processedMarkdown = markdown
    ? markdown.replace(
        /!\[([^\]]*)\]\(charts\/([^)]+)\)/g,
        `![$1](${base}/charts/$2)`,
      )
    : "";

  /** Render inline citation refs [c1] [c2] as superscript badges */
  function renderTextWithCitations(text: string): React.ReactNode {
    const parts = text.split(/(\[c\d+\])/g);
    if (parts.length === 1) return text;
    return parts.map((part, i) => {
      const m = part.match(/^\[c(\d+)\]$/);
      if (m) {
        return (
          <sup key={i} className="canvas__cite" title={`引用 ${m[1]}`}>
            {m[1]}
          </sup>
        );
      }
      return part;
    });
  }

  return (
    <div className="canvas">
      {/* Header */}
      <div className="canvas__header">
        <div className="canvas__title">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
            <path d="M14 2v6h6" />
          </svg>
          <span>研报预览{version ? ` · v${version}` : " · 最新版"}</span>
        </div>
        <div className="canvas__actions">
          <a className="canvas__action-btn" href={`${base}/pdf`} download title="下载 PDF">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            PDF
          </a>
          <a className="canvas__action-btn" href={`${base}/markdown`} download title="下载 Markdown">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            MD
          </a>
          <button
            type="button"
            className="canvas__close"
            onClick={onClose}
            aria-label="关闭预览"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="canvas__body">
        {loading && (
          <div className="canvas__loading">
            <div className="spinner" />
            <span>加载报告中…</span>
          </div>
        )}
        {error && <div className="canvas__error">{error}</div>}
        {!loading && !error && markdown && (
          <div className="canvas__layout">
            <article className="canvas__article">
              {/* @ts-expect-error react-markdown types mismatch with React 18 */}
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => {
                    // Transform [c1] citations to superscript in paragraph text
                    const processed = React.Children.map(children as React.ReactNode, (child) => {
                      if (typeof child === "string") {
                        return renderTextWithCitations(child);
                      }
                      return child;
                    });
                    return <p>{processed}</p>;
                  },
                  li: ({ children }) => {
                    const processed = React.Children.map(children as React.ReactNode, (child) => {
                      if (typeof child === "string") {
                        return renderTextWithCitations(child);
                      }
                      return child;
                    });
                    return <li>{processed}</li>;
                  },
                  h2: ({ children }) => {
                    const text = typeof children === 'string' ? children : String(children);
                    const id = text.toLowerCase().replace(/\s+/g, '-').replace(/[（）]/g, '');
                    return <h2 id={id}>{children as React.ReactNode}</h2>;
                  },
                  img: ({ src, alt }) => (
                    <figure className="canvas__figure">
                      <img src={src} alt={alt || ""} loading="lazy" onClick={() => setLightboxSrc(src || null)} style={{cursor: 'pointer'}} />
                      {alt && <figcaption>{alt}</figcaption>}
                    </figure>
                  ),
                  table: ({ children }) => (
                    <div className="canvas__table-wrap">
                      <table>{children as React.ReactNode}</table>
                    </div>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote className="canvas__blockquote">
                      {children as React.ReactNode}
                    </blockquote>
                  ),
                }}
              >
                {processedMarkdown}
              </ReactMarkdown>
            </article>
            {headings.length > 2 && (
              <nav className="canvas__toc">
                <div className="canvas__toc-title">目录</div>
                {headings.map((h, i) => (
                  <a key={i} className="canvas__toc-item" href={`#${h.toLowerCase().replace(/\s+/g, '-')}`}
                     onClick={(e) => { e.preventDefault(); document.getElementById(h.toLowerCase().replace(/\s+/g, '-').replace(/[（）]/g, ''))?.scrollIntoView({behavior: 'smooth'}); }}>
                    {h}
                  </a>
                ))}
              </nav>
            )}
          </div>
        )}
      </div>

      {lightboxSrc && (
        <div className="lightbox" onClick={() => setLightboxSrc(null)}>
          <img src={lightboxSrc} alt="" />
          <button className="lightbox__close" onClick={() => setLightboxSrc(null)}>×</button>
        </div>
      )}
    </div>
  );
}
