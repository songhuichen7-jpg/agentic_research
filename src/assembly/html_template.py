"""HTML template for PDF report export."""

REPORT_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  @page {{
    size: A4;
    margin: 2.5cm 2cm;
    @top-center {{ content: "{short_title}"; font-size: 9pt; color: #888; }}
    @bottom-center {{ content: "第 " counter(page) " 页"; font-size: 9pt; color: #888; }}
  }}
  body {{
    font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "WenQuanYi Micro Hei", sans-serif;
    font-size: 11pt;
    line-height: 1.8;
    color: #333;
    max-width: 100%;
  }}
  h1 {{
    font-size: 22pt;
    color: #1a365d;
    border-bottom: 3px solid #2b6cb0;
    padding-bottom: 12px;
    margin-top: 40px;
    page-break-before: avoid;
  }}
  h2 {{
    font-size: 16pt;
    color: #2b6cb0;
    border-bottom: 1px solid #bee3f8;
    padding-bottom: 6px;
    margin-top: 30px;
    page-break-after: avoid;
  }}
  h3 {{
    font-size: 13pt;
    color: #2c5282;
    margin-top: 20px;
  }}
  blockquote {{
    border-left: 4px solid #bee3f8;
    padding: 8px 16px;
    margin: 16px 0;
    background: #ebf8ff;
    color: #2a4365;
    font-size: 10pt;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
    font-size: 10pt;
  }}
  th, td {{
    border: 1px solid #cbd5e0;
    padding: 8px 12px;
    text-align: left;
  }}
  th {{
    background: #ebf8ff;
    font-weight: 600;
    color: #2c5282;
  }}
  tr:nth-child(even) {{
    background: #f7fafc;
  }}
  img {{
    max-width: 100%;
    height: auto;
    display: block;
    margin: 16px auto;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
  }}
  .cover {{
    text-align: center;
    padding: 80px 20px 40px;
    page-break-after: always;
  }}
  .cover h1 {{
    font-size: 28pt;
    border: none;
    color: #1a365d;
    margin-bottom: 20px;
  }}
  .cover .meta {{
    font-size: 11pt;
    color: #718096;
    margin-top: 30px;
    line-height: 2;
  }}
  .toc {{
    page-break-after: always;
  }}
  .toc a {{
    color: #2b6cb0;
    text-decoration: none;
  }}
  .toc li {{
    margin: 8px 0;
    font-size: 12pt;
  }}
  .references {{
    font-size: 10pt;
    line-height: 1.6;
  }}
  .references li {{
    margin: 4px 0;
    word-break: break-all;
  }}
  .disclaimer {{
    font-size: 9pt;
    color: #a0aec0;
    text-align: center;
    margin-top: 40px;
    padding-top: 16px;
    border-top: 1px solid #e2e8f0;
  }}
  a {{
    color: #2b6cb0;
    text-decoration: none;
  }}
  code {{
    background: #edf2f7;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.9em;
  }}
  em {{
    font-style: italic;
    color: #4a5568;
  }}
  strong {{
    color: #1a202c;
  }}
  hr {{
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 24px 0;
  }}
</style>
</head>
<body>
{body}
</body>
</html>
"""
