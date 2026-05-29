FROM python:3.11-slim

# Force cache bust - change this value to trigger a full rebuild
ARG CACHE_BUST=2026-05-28-v3

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    gcc \
    g++ \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data \
    && useradd -m -s /bin/bash potato

COPY requirements.server.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.server.txt

COPY . .

RUN chown -R potato:potato /app /data

ENV PORT=8080 \
    PYTHONUNBUFFERED=1 \
    POTATO_ENABLE_SCHEDULER=true \
    POTATO_CYCLE_MINUTES=3 \
    POTATO_INTEL_ENABLED=true

EXPOSE 8080
USER potato

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]