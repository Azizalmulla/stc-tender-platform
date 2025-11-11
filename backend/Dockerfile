FROM python:3.10-slim

WORKDIR /app

# Install system dependencies including Chrome for Puppeteer
RUN apt-get update && apt-get install -y \
    postgresql-client \
    tesseract-ocr \
    tesseract-ocr-ara \
    libpq-dev \
    gcc \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libxss1 \
    libappindicator3-1 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# Set Chrome executable path for Pyppeteer
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Make startup script executable
RUN chmod +x start.sh

# Expose port
EXPOSE 8000

# Run with startup script
CMD ["./start.sh"]
