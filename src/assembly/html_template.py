"""HTML template for PDF report export — institutional research report style."""

REPORT_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  @page {{
    size: A4;
    margin: 2.2cm 1.8cm 2.2cm 1.8cm;
    @top-left {{
      content: "{short_title}";
      font-family: "Source Han Sans SC", "Noto Sans CJK SC", "PingFang SC", sans-serif;
      font-size: 8pt;
      color: #64748b;
      padding-top: 0.5cm;
    }}
    @top-right {{
      content: "行业研究";
      font-family: "Source Han Sans SC", "Noto Sans CJK SC", "PingFang SC", sans-serif;
      font-size: 8pt;
      color: #64748b;
      padding-top: 0.5cm;
    }}
    @bottom-center {{
      content: counter(page) " / " counter(pages);
      font-family: "Source Han Sans SC", "Noto Sans CJK SC", "PingFang SC", sans-serif;
      font-size: 8pt;
      color: #94a3b8;
    }}
    @bottom-left {{
      content: "Research Report";
      font-family: "Source Han Sans SC", "Noto Sans CJK SC", "PingFang SC", sans-serif;
      font-size: 7pt;
      color: #cbd5e1;
    }}
    @bottom-right {{
      content: "机密 · 仅供参考";
      font-family: "Source Han Sans SC", "Noto Sans CJK SC", "PingFang SC", sans-serif;
      font-size: 7pt;
      color: #cbd5e1;
    }}
  }}

  @page :first {{
    margin: 0;
    @top-left {{ content: ""; }}
    @top-right {{ content: ""; }}
    @bottom-center {{ content: ""; }}
    @bottom-left {{ content: ""; }}
    @bottom-right {{ content: ""; }}
  }}

  * {{
    box-sizing: border-box;
  }}

  body {{
    font-family: "Source Han Serif SC", "Noto Serif CJK SC", "Songti SC", "SimSun", "PingFang SC", serif;
    font-size: 10.5pt;
    line-height: 1.75;
    color: #0f172a;
    margin: 0;
    padding: 0;
  }}

  /* ─────────────────────────────────────────────────────────
     Cover page
     ───────────────────────────────────────────────────────── */
  .cover {{
    page-break-after: always;
    position: relative;
    height: 100vh;
    background: #0B2545;
    color: white;
    padding: 0;
    margin: 0;
  }}

  .cover__brand {{
    position: absolute;
    top: 2.5cm;
    left: 2cm;
    right: 2cm;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }}

  .cover__brand-name {{
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
    font-size: 10pt;
    letter-spacing: 2px;
    color: #D4AF37;
    text-transform: uppercase;
  }}

  .cover__brand-tag {{
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
    font-size: 9pt;
    color: rgba(255,255,255,0.6);
    text-align: right;
  }}

  .cover__title-block {{
    position: absolute;
    top: 8cm;
    left: 2cm;
    right: 2cm;
  }}

  .cover__label {{
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
    font-size: 10pt;
    color: #D4AF37;
    letter-spacing: 3px;
    margin-bottom: 0.6cm;
  }}

  .cover__main-title {{
    font-family: "Source Han Serif SC", "Noto Serif CJK SC", serif;
    font-size: 28pt;
    font-weight: 700;
    color: white;
    line-height: 1.3;
    margin: 0 0 0.8cm 0;
    letter-spacing: -0.5px;
  }}

  .cover__subtitle {{
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
    font-size: 11pt;
    color: rgba(255,255,255,0.75);
    font-weight: 400;
    margin-top: 0.3cm;
  }}

  .cover__rule {{
    width: 4cm;
    height: 2px;
    background: #D4AF37;
    margin: 1cm 0;
  }}

  .cover__meta {{
    position: absolute;
    bottom: 3cm;
    left: 2cm;
    right: 2cm;
    display: flex;
    gap: 2cm;
    padding-top: 1cm;
    border-top: 1px solid rgba(255,255,255,0.15);
  }}

  .cover__meta-item {{
    flex: 1;
  }}

  .cover__meta-label {{
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
    font-size: 8pt;
    color: rgba(255,255,255,0.5);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 0.2cm;
  }}

  .cover__meta-value {{
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
    font-size: 10pt;
    color: white;
    font-weight: 500;
  }}

  /* ─────────────────────────────────────────────────────────
     Main content typography
     ───────────────────────────────────────────────────────── */
  h1 {{
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
    font-size: 20pt;
    font-weight: 700;
    color: #0B2545;
    margin: 0 0 0.4cm 0;
    padding: 0;
    letter-spacing: -0.3px;
    page-break-before: avoid;
  }}

  h2 {{
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
    font-size: 14pt;
    font-weight: 700;
    color: #0B2545;
    margin: 1.2cm 0 0.4cm 0;
    padding-bottom: 0.25cm;
    border-bottom: 2px solid #0B2545;
    page-break-after: avoid;
    position: relative;
  }}

  h3 {{
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
    font-size: 12pt;
    font-weight: 600;
    color: #1e3a5f;
    margin: 0.8cm 0 0.3cm 0;
    page-break-after: avoid;
    border-left: 3px solid #D4AF37;
    padding-left: 0.3cm;
  }}

  h4 {{
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
    font-size: 10.5pt;
    font-weight: 600;
    color: #334155;
    margin: 0.5cm 0 0.2cm 0;
  }}

  p {{
    margin: 0 0 0.35cm 0;
    text-align: justify;
    text-justify: inter-ideograph;
  }}

  strong {{
    color: #0B2545;
    font-weight: 700;
  }}

  em {{
    font-style: italic;
    color: #475569;
  }}

  /* ─────────────────────────────────────────────────────────
     Blockquotes (key callouts)
     ───────────────────────────────────────────────────────── */
  blockquote {{
    border-left: 4px solid #D4AF37;
    background: #FFF9E6;
    margin: 0.5cm 0;
    padding: 0.35cm 0.5cm;
    font-size: 10pt;
    color: #1e293b;
    line-height: 1.65;
    page-break-inside: avoid;
  }}

  blockquote p {{
    margin: 0;
  }}

  blockquote strong {{
    color: #8B6F00;
  }}

  /* ─────────────────────────────────────────────────────────
     Tables (institutional style)
     ───────────────────────────────────────────────────────── */
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 0.5cm 0;
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
    font-size: 9.5pt;
    page-break-inside: avoid;
  }}

  thead {{
    background: #0B2545;
    color: white;
  }}

  th {{
    padding: 0.25cm 0.35cm;
    text-align: left;
    font-weight: 600;
    font-size: 9pt;
    letter-spacing: 0.3px;
    border: none;
  }}

  td {{
    padding: 0.22cm 0.35cm;
    border-bottom: 1px solid #e2e8f0;
    color: #1e293b;
  }}

  tbody tr:nth-child(even) {{
    background: #f8fafc;
  }}

  tbody tr:hover {{
    background: #f1f5f9;
  }}

  /* Right-align numeric columns (last column usually) */
  td:last-child {{
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }}

  /* ─────────────────────────────────────────────────────────
     Lists
     ───────────────────────────────────────────────────────── */
  ul, ol {{
    margin: 0.3cm 0 0.4cm 0.6cm;
    padding: 0;
  }}

  li {{
    margin: 0.15cm 0;
    line-height: 1.7;
  }}

  ul li::marker {{
    color: #D4AF37;
  }}

  /* ─────────────────────────────────────────────────────────
     Images / Charts
     ───────────────────────────────────────────────────────── */
  img {{
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0.4cm auto;
    page-break-inside: avoid;
  }}

  /* Chart caption style (the italic line after an image) */
  p em {{
    display: block;
    text-align: center;
    font-size: 9pt;
    color: #64748b;
    margin-top: -0.2cm;
    margin-bottom: 0.5cm;
  }}

  /* ─────────────────────────────────────────────────────────
     TOC
     ───────────────────────────────────────────────────────── */
  .toc {{
    page-break-after: always;
    padding-top: 0.5cm;
  }}

  .toc h2 {{
    font-size: 18pt;
    border: none;
    margin-bottom: 1cm;
    padding: 0;
  }}

  .toc ol {{
    list-style: none;
    margin: 0;
    padding: 0;
    counter-reset: toc-counter;
  }}

  .toc li {{
    margin: 0.35cm 0;
    padding: 0.2cm 0;
    border-bottom: 1px dotted #cbd5e1;
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
    font-size: 11pt;
    counter-increment: toc-counter;
  }}

  .toc li::before {{
    content: counter(toc-counter, decimal-leading-zero) "  ";
    color: #D4AF37;
    font-weight: 700;
    margin-right: 0.3cm;
  }}

  .toc a {{
    color: #0B2545;
    text-decoration: none;
  }}

  /* ─────────────────────────────────────────────────────────
     References
     ───────────────────────────────────────────────────────── */
  .references {{
    font-size: 9pt;
    line-height: 1.6;
    color: #475569;
  }}

  .references li {{
    margin: 0.15cm 0;
    word-break: break-all;
  }}

  /* ─────────────────────────────────────────────────────────
     Disclaimer
     ───────────────────────────────────────────────────────── */
  .disclaimer {{
    font-size: 8pt;
    color: #94a3b8;
    margin-top: 1cm;
    padding-top: 0.4cm;
    border-top: 1px solid #e2e8f0;
    line-height: 1.6;
    font-family: "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
  }}

  /* ─────────────────────────────────────────────────────────
     Horizontal rules
     ───────────────────────────────────────────────────────── */
  hr {{
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 0.8cm 0;
  }}

  /* Citation references rendered as superscript badges */
  sup, .citation {{
    font-size: 7.5pt;
    color: #2563eb;
    font-weight: 600;
    vertical-align: super;
    line-height: 0;
  }}

  a {{
    color: #2563eb;
    text-decoration: none;
  }}

  code {{
    font-family: "SF Mono", "JetBrains Mono", Consolas, monospace;
    background: #f1f5f9;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 9pt;
    color: #0B2545;
  }}
</style>
</head>
<body>
{body}
</body>
</html>
"""
