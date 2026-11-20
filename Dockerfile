# Stage 1: Build the Vue application
FROM node:22-alpine AS frontend-builder
WORKDIR /web-ui
COPY web-ui/package*.json ./
RUN npm ci
COPY web-ui/ .
RUN npm run build

# Stage 2: Create the final, lean image
FROM python:3.11-slim-bookworm

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    RUNNING_IN_DOCKER=true \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    TZ=Asia/Shanghai

# 依赖直接装进本镜像的 Python，不再跨阶段拷贝 venv。
# 旧写法用 `COPY --from=builder /opt/venv` 复用 venv：拷贝一旦没落地，
# 后面的 playwright 就退化成「命令未找到」(exit 127)，日志里也看不出原因。
COPY requirements-runtime.txt .

RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-runtime.txt

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tzdata \
        tini \
        libzbar0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN python -m playwright install --with-deps --no-shell chromium \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=frontend-builder /dist /app/dist

COPY src /app/src
COPY spider_v2.py /app/spider_v2.py
COPY prompts /app/prompts
COPY static /app/static
COPY config.json.example /app/config.json.example

RUN mkdir -p /app/data /app/state /app/logs /app/images /app/jsonl /app/price_history

EXPOSE 8000

USER root

ENTRYPOINT ["tini", "--"]

CMD ["python", "-m", "src.app"]
