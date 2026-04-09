# ── Build stage: install deps + build frontend ──────────────────
FROM python:3.12-slim AS builder

# WeasyPrint 系统依赖 (Debian Bookworm)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm \
    libpangocairo-1.0-0 libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
    libffi-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# 安装前端依赖 + 构建
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

COPY . .
RUN cd frontend && npm run build

# ── Runtime stage ───────────────────────────────────────────────
FROM python:3.12-slim

# WeasyPrint 运行时依赖 (Debian Bookworm)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpangocairo-1.0-0 libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 从 builder 拷贝
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/src ./src
COPY --from=builder /app/frontend/dist ./frontend/dist
COPY --from=builder /app/scripts ./scripts
COPY --from=builder /app/pyproject.toml ./

# 创建运行时目录
RUN mkdir -p data/raw data/parsed data/evidence data/charts data/reports data/runs db cache

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080

CMD ["sh", "-c", "uvicorn src.api.server:app --host 0.0.0.0 --port ${PORT:-8080} --log-level info"]
