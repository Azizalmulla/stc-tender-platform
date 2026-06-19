FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    tesseract-ocr \
    tesseract-ocr-ara \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Phase 0/1: install Chromium + its OS dependencies so the FREE local Playwright
# screenshot path actually works. Without this, every flipbook screenshot falls
# through to the PAID Browserless fallback, defeating cost control.
# We install the runtime libs explicitly instead of `playwright install --with-deps`
# because Playwright's bundled dep list still references font packages
# (ttf-unifont / ttf-ubuntu-font-family) that no longer exist in Debian bookworm.
# Fonts include Arabic-capable sets for correct gazette page rendering before OCR.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
        libdrm2 libxkbcommon0 libatspi2.0-0 libx11-6 libxcomposite1 libxdamage1 \
        libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        libxcb1 libxshmfence1 \
        fonts-liberation fonts-unifont fonts-noto-core \
    && rm -rf /var/lib/apt/lists/* \
    && python -m playwright install chromium

# PostgreSQL client 17 from the official PGDG repo.
# ops/backup.sh runs `pg_dump` inside this image. pg_dump REFUSES to dump a server
# NEWER than itself, and Debian bookworm only ships client 15 — too old for our
# targets (Neon runs PG16/17; the self-hosted compose profile uses pg16). A client
# >= the server always works, so we install 17 (dumps 14/15/16/17 servers fine).
# pg_wrapper then routes /usr/bin/pg_dump to the newest installed version (17).
# Kept as a late layer so it never invalidates the cached pip/Chromium layers.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-17 \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . .

# Make startup script executable
RUN chmod +x start.sh

# Expose port
EXPOSE 8000

# Run with startup script
CMD ["./start.sh"]
