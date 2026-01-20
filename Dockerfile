FROM python:3.11-slim-bookworm

WORKDIR /app

# 1. Install system dependencies
# required for building python packages and for Playwright
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libssl-dev \
    pkg-config \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Install Playwright Browsers
# This installs chromium and its system dependencies
RUN playwright install --with-deps chromium

# 3. Code
COPY . .

# Cloud Run expects the container to listen on $PORT
# We default to 8080 if not set
ENV PORT=8080

# Run Uvicorn
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}