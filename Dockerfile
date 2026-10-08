FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       gcc \
       g++ \
       libgl1 \
       libglib2.0-0 \
       libsm6 \
       libxext6 \
       libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY api ./api
COPY analytics ./analytics
COPY dashboard ./dashboard
COPY db ./db
COPY detection ./detection
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --upgrade pip setuptools wheel \
    && pip install -e ".[test,cv]"

RUN useradd --create-home --uid 10001 sentinel \
    && chown -R sentinel:sentinel /app

USER sentinel

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/live', timeout=3)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
