FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    HF_HUB_OFFLINE=1 \
    ORT_DISABLE_TELEMETRY=1 \
    GRADIO_ANALYTICS_ENABLED=False

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation2 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-lock.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt

COPY build_medical_embeddings.py search_medical_embeddings.py ./
COPY web_app ./web_app

RUN useradd --uid 10001 --create-home appuser \
    && mkdir -p /app/documents /app/embedings /app/model_cache \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/healthz', timeout=4)" || exit 1
CMD ["uvicorn", "web_app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
