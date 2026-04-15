# Agentic Research Report Generator

机构级行业研报自动生成系统。基于 LangGraph 编排 9 节点流水线，结合多源数据采集、真实市场数据、智能图表规划、多轮修订和版本管理，一键生成带专业封面、执行摘要、投资评级的行业深度研报 PDF。

## 核心特性

### 数据与写作
- **多源数据采集**：东方财富行业研报 + 博查搜索 + AkShare 申万行业指数
- **真实市场数据接入**：AkShare 自动映射主题到申万一级行业（31 个），抓取月度指数走势和跨行业 PE 对比做成图表
- **混合检索**：OpenAI embeddings（`text-embedding-3-small`）+ BM25 关键词检索
- **并行章节写作**：6 路并发调用 LLM 同时写多个章节（原先是串行），速度提升 3-4 倍
- **数据密度硬要求**：prompt 强制每段 2 个具体数字，禁用"较高/快速/显著"等模糊词

### 报告质量
- **专业封面页**：深蓝 + 金色装饰，像券商研报
- **执行摘要**：投资评级（强烈推荐 / 推荐 / 中性 / 回避）+ 核心观点 + 投资要点 + 核心指标表
- **行业分析框架**：PEST、波特五力、产业链、生命周期、TAM/SAM/SOM 等 8 个框架按行业自动注入
- **智能图表**：最多 4 张，真实数据优先 + LLM 从正文提取 + 零值过滤
- **PDF 导出**：WeasyPrint 渲染，思源宋体正文，页眉页脚，A4 版式

### 交互与体验
- **SSE 流式事件**：前端实时显示流水线进度（9 节点）
- **Canvas 预览**：聊天界面旁展开报告预览，支持目录跳转、图片 lightbox、引用上标
- **多轮修订**：报告生成后可发起修改对话，系统自动判断是"纯改写"还是"需补数据搜索"
- **版本管理**：每次修改保存历史版本，可对比查看 v1 / v2 / latest
- **苹果风格 UI**：浅色主题 + 毛玻璃侧边栏 + 暗色模式（跟随系统）+ 键盘快捷键

## 工作流水线

```
用户输入主题
  → [1] 采集研报（东方财富）
  → [2] 生成研究大纲（LLM + 行业分析框架自动注入）
  → [3] 博查搜索补充证据（空结果自动重试，跳过缓存）
  → [4] 证据分块 + 向量入库（OpenAI embedding）
  → [5] 并行写作 6-8 章节（带 [cN] 引用标注）
  → [6] 图表规划（真实数据 + LLM 提取 + 零值过滤）
  → [7] 组装报告（封面 + 执行摘要 + 正文 + 参考）
  → [8] 质量检查（引用覆盖率、字数、证据密度）
  → [9] 导出 PDF
```

## 快速开始

### 环境要求
- Python 3.12+
- Node.js 18+
- Docker（生产部署）

### 本地开发

```bash
# 克隆
git clone https://github.com/songhuichen7-jpg/agentic_research.git
cd agentic_research

# 后端
uv sync
# 前端
cd frontend && npm install && cd ..

# 配置 API Key（见下）
cp .env.example .env
# 编辑 .env 填入你的 key

# 启动后端
uv run uvicorn src.api.server:app --reload --port 8000

# 启动前端（另一个终端）
cd frontend && npm run dev
```

前端默认 `http://localhost:5173`，API 默认 `http://localhost:8000`

### 环境变量

```env
# LLM API（OpenAI 兼容，可用 OpenRouter / 小爱 / 直连 OpenAI）
OPENROUTER_API_KEY=sk-...
LLM_BASE_URL=https://xiaoai.plus/v1      # 可选，默认小爱中转

# 模型选择（可选）
WRITER_MODEL=gpt-4o                       # 写作模型
UTILITY_MODEL=gpt-4o                      # 工具模型
EMBEDDING_MODEL=text-embedding-3-small    # 向量化

# 博查搜索
BOCHA_API_KEY=sk-...

# 服务配置
PORT=8080
CORS_ORIGINS=https://your-domain.com      # 生产环境
```

### Docker 部署

```bash
# 构建镜像
docker build -t agentic-research .

# 运行
docker run -d \
  --name agentic-research \
  -p 8080:8080 \
  -e OPENROUTER_API_KEY='...' \
  -e BOCHA_API_KEY='...' \
  -e WRITER_MODEL='gpt-4o' \
  -e UTILITY_MODEL='gpt-4o' \
  -e EMBEDDING_MODEL='text-embedding-3-small' \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/db:/app/db \
  agentic-research
```

生产部署到云服务器（如阿里云 ECS），建议：
1. 本地构建 x86 镜像：`docker buildx build --platform linux/amd64`
2. 推送到 ACR：`docker push YOUR_ACR/agentic-research`
3. 服务器 pull + run
4. 挂载持久卷到 `/app/data` 和 `/app/db`

## 项目结构

```
src/
├── api/server.py              # FastAPI：SSE、REST、历史、修订、版本
├── graph/
│   ├── workflow.py            # LangGraph 9 节点编排 + 并行章节写作
│   └── nodes/planner.py       # 大纲生成（带行业框架注入）
├── connectors/
│   ├── eastmoney.py           # 东方财富研报
│   ├── bocha_search.py        # 博查网页搜索（含网页正文抓取）
│   └── akshare_connector.py   # A/HK 股价、申万行业数据
├── parsers/                   # HTML / PDF 解析
├── evidence/
│   ├── chunker.py             # 中文智能分块
│   └── store.py               # Chroma + 可切换 API embedding
├── retrieval/
│   ├── retriever.py           # BM25 + 向量混合检索
│   └── citation.py            # 引用去重
├── writers/
│   ├── section_writer.py      # 流式章节写作（含 chart_suggestions 清理）
│   ├── executive_summary.py   # 执行摘要生成（评级 + 核心指标）
│   └── reviser.py             # 多轮修订（意图分类 + edit/research 分支）
├── charts/
│   ├── planner.py             # 图表规划（真实数据 + LLM 提取）
│   ├── real_data.py           # AkShare 真实市场数据抓取
│   └── renderer.py            # Matplotlib 专业配色渲染
├── analysis/
│   ├── frameworks.py          # 8 个行业分析框架自动选择
│   └── calculator.py          # 指标自动计算
├── assembly/
│   ├── assembler.py           # 报告装配（封面 + 摘要 + 章节）
│   ├── html_template.py       # 机构级 PDF 模板（深蓝+金色）
│   └── pdf_export.py          # WeasyPrint PDF 导出
├── quality/checker.py         # 引用覆盖率 + 字数 + 证据密度
├── config/
│   ├── settings.py            # 环境变量配置
│   └── llm.py                 # LLM 工厂（OpenAI 兼容）
├── telemetry/run_events.py    # SSE 事件总线
└── db.py                      # SQLite 运行记录

frontend/src/
├── App.tsx                    # 主应用（聊天 + 侧边栏 + Canvas）
├── components/
│   ├── CanvasPanel.tsx        # 报告预览 Canvas（TOC、lightbox、引用上标）
│   ├── PipelineFlowchart.tsx  # 流水线进度条
│   ├── ConsoleLog.tsx         # SSE 事件流展示
│   └── HistoryPanel.tsx       # 历史记录侧边栏
├── hooks/useRunStream.ts      # SSE 订阅 + 状态管理
└── state/pipelineReducer.ts   # Pipeline reducer
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 写作模型 | GPT-4o / DeepSeek V3 / Gemini 2.5 Flash（OpenAI 兼容，可切换） |
| 向量化 | `text-embedding-3-small`（API）或本地 all-MiniLM（可切换） |
| 后端 | Python 3.12, FastAPI, LangGraph, LangChain, uv |
| 数据 | Chroma（向量）+ BM25（关键词）+ SQLite（运行记录） |
| 真实数据 | AkShare（申万行业指数、PE/PB、成分股） |
| 图表 | Matplotlib（专业配色 + CJK 字体） |
| PDF | WeasyPrint + 思源宋体 + A4 版式 |
| 前端 | Vite 5, React 18, TypeScript, react-markdown |
| 部署 | Docker（多阶段构建，含中文字体 + WeasyPrint 系统依赖） |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/report/run` | 提交新研报任务 |
| GET | `/api/report/{run_id}/stream` | SSE 事件流 |
| POST | `/api/report/{run_id}/revise` | 多轮修订（智能判断意图） |
| GET | `/api/report/{run_id}/markdown?v=N` | 下载指定版本 Markdown |
| GET | `/api/report/{run_id}/pdf` | 下载 PDF |
| GET | `/api/report/{run_id}/artifacts` | 图表资源列表 |
| GET | `/api/report/{run_id}/cancel` | 取消任务 |
| GET | `/api/runs` | 历史记录 |
| DELETE | `/api/runs/{run_id}` | 删除运行 |
| GET | `/api/health` | 健康检查 |

## License

MIT
