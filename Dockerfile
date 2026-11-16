# One container that runs the whole app (web, background work, SQLite database). Works on Render, Fly.io, Railway, Cloud Run,
# any server with Docker, and on a laptop:   docker run -p 8000:8000 -v talentbridge-data:/data ghcr.io/OWNER/REPO
# For the larger set-up (PostgreSQL, separate worker, local AI model, https) use compose.yaml and docs/DEPLOY.md.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    UPLOAD_DIR=/data/uploads \
    HOST=0.0.0.0 \
    PORT=8000 \
    DEMO_SEED=0

WORKDIR /app
# Tesseract reads scanned (image-only) CVs; gosu lets the entrypoint fix volume permissions and then drop root
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng gosu \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-prod.txt requirements-postgres.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt \
    && groupadd --system talentbridge \
    && useradd --system --gid talentbridge --home-dir /app talentbridge \
    && mkdir -p /data \
    && chown talentbridge:talentbridge /data

COPY run.py ./run.py
COPY sample_data ./sample_data
COPY backend ./backend
COPY frontend ./frontend
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && chown -R talentbridge:talentbridge /app

VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=8s --start-period=90s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/v1/health', timeout=5)"
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "/app/run.py"]
