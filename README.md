# Agentic Research Report Generator

自动化行业研报生成系统，基于 LangGraph 编排，支持 LLM 流式写作、多源数据采集、智能图表生成。

## 功能

- **多源数据采集**：东方财富行业研报 + 博查网页搜索，自动去重与缓存
- **智能章节写作**：LLM 流式输出，实时展示写作进度，带引用标注 [c1][c2]
- **混合检索**：Chroma 向量检索 + BM25 关键词检索，Top-K 证据召回
- **10 种图表类型**：柱状图、折线图、饼图、表格、时间线、关键词云、KPI 卡片、产业链图、对比矩阵
- **PDF 导出**：WeasyPrint 渲染，支持中文排版
- **Web 控制台**：SSE 实时事件流，流水线可视化，历史管理，协作式取消
- **质量检查**：自动检测引用缺失、内容过短等问题

## 演示

GitHub 仓库主页的 README **不支持内嵌播放** `.mov` 视频（会忽略 `<video>` 标签），请在下述页面打开后使用 GitHub 自带的播放器观看或下载：

**[▶ 在浏览器中观看演示（演示.mov）](https://github.com/songhuichen7-jpg/agentic_research/blob/master/%E6%BC%94%E7%A4%BA.mov)**

本地克隆后若该文件只有几行文本（LFS 指针），请先安装 [Git LFS](https://git-lfs.com/) 并执行 `git lfs pull` 再播放。

## 架构

```
用户输入主题
  → 采集研报与元数据（东方财富 + 博查搜索）
  → LLM 生成研究大纲与章节
  → 证据分块与向量入库
  → 分章写作（流式 LLM，带引用标注）
  → 图表规划与渲染（数据图 + 可视化图）
  → 组装 Markdown 报告
  → 质量检查
  → 导出 PDF
```

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+

### 安装

```bash
# 克隆仓库
git clone https://github.com/songhuichen7-jpg/agentic_research.git
cd agentic_research

# 创建虚拟环境并安装依赖
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 安装前端依赖
cd frontend && npm install && cd ..
```

### 配置

创建 `.env` 文件：

```env
OPENROUTER_API_KEY=your_key_here
BOCHA_API_KEY=your_key_here
```

### 启动

```bash
# 构建前端 + 启动后端
./scripts/serve_web.sh

# 或手动启动
cd frontend && npm run build && cd ..
uvicorn src.api.server:app --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000

### CLI 模式

```bash
python scripts/run_report.py "低空经济"
```

## 项目结构

```
src/
├── api/              # FastAPI 服务（SSE, REST, 历史管理）
├── graph/            # LangGraph 工作流（9 节点）
├── connectors/       # 数据源（东方财富、博查搜索、AkShare）
├── parsers/          # HTML / PDF 解析
├── evidence/         # 中文分块 + Chroma 向量存储
├── retrieval/        # BM25 + 向量混合检索
├── writers/          # LLM 流式章节写作
├── charts/           # 图表规划 + Matplotlib 渲染
├── assembly/         # Markdown 装配 + PDF 导出
├── quality/          # 质量检查
├── config/           # 配置 + LLM 工厂
├── telemetry/        # RunEventBus 事件总线
├── analysis/         # 启发式指标计算
└── db.py             # SQLite 运行记录
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.12, FastAPI, LangGraph, LangChain |
| LLM | OpenRouter (deepseek-v3.2 / gemini-3.1-flash-lite) |
| 前端 | Vite 5, React 18, TypeScript, Framer Motion |
| 数据 | SQLite, Chroma, BM25 |
| 图表 | Matplotlib (10 种图表类型) |
| PDF | WeasyPrint |

## License

MIT
