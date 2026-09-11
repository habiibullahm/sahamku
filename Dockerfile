FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Jakarta \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# Dependencies dulu supaya layer ter-cache
COPY pyproject.toml README.md ./
COPY sahamku ./sahamku
RUN pip install --upgrade pip && pip install .

COPY scripts ./scripts
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Data persisten (DB + chart) di volume
ENV DB_PATH=/data/sahamku.db \
    CHARTS_DIR=/data/charts
VOLUME ["/data"]

ENTRYPOINT ["/entrypoint.sh"]
