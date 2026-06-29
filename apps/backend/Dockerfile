# ═══════════════════════════════════════════════════════════════
#  阶段1: 构建（安装依赖、编译 pyc）
# ═══════════════════════════════════════════════════════════════
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY core/ core/
COPY audiences/ audiences/
COPY scripts/ scripts/
COPY plugins/ plugins/
COPY railway-start.sh .

RUN python -m compileall -q core/ audiences/ scripts/ plugins/

# ═══════════════════════════════════════════════════════════════
#  阶段2: 运行（精简镜像）
# ═══════════════════════════════════════════════════════════════
FROM python:3.11-slim

WORKDIR /app

# 安装运行时库（含 OpenCV 依赖）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        libxcb1 \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /build /app

# 预下载 NLTK 数据 + 日志目录 + 非 root 用户
RUN python -c "import nltk; nltk.download('punkt_tab', download_dir='/app/nltk_data')" && \
    mkdir -p /app/log && \
    useradd --no-create-home --shell /usr/sbin/nologin appuser && \
    chown -R appuser:appuser /app

ENV NLTK_DATA=/app/nltk_data
ENV LOG_DIR=/app/log
ENV MEMORIES_DIR=/app/memories

USER appuser

EXPOSE 8080

CMD ["./railway-start.sh"]
