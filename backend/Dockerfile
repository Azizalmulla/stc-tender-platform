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

# Copy application code
COPY . .

# Make startup script executable
RUN chmod +x start.sh

# Expose port
EXPOSE 8000

# Run with startup script
CMD ["./start.sh"]
