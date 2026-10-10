FROM node:22-slim AS frontend-build
WORKDIR /frontend
COPY src/frontend/package.json src/frontend/package-lock.json* ./
RUN npm install
COPY src/frontend/ ./
ARG PUBLIC_BASE_PATH=""
ENV PUBLIC_BASE_PATH=${PUBLIC_BASE_PATH}
RUN npm run build

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONPATH=/app/src \
    HF_HUB_OFFLINE=1 \
    ORT_DISABLE_TELEMETRY=1 \
    FRONTEND_DIST_DIR=/app/src/frontend/dist

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation2 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-lock.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt

COPY pyproject.toml README.md ./
COPY src/backend ./src/backend
COPY src/scripts ./src/scripts
COPY medicina-naturista-documente/data/medical_conditions.jsonl ./medicina-naturista-documente/data/medical_conditions.jsonl
COPY medicina-naturista-documente/data/herbs.jsonl ./medicina-naturista-documente/data/herbs.jsonl
COPY --from=frontend-build /frontend/dist ./src/frontend/dist

RUN useradd --uid 10001 --create-home appuser \
    && mkdir -p /app/medicina-naturista-documente/data/documents /app/model_cache \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/healthz', timeout=4)" || exit 1
CMD ["uvicorn", "backend.web.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
