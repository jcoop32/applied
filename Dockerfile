FROM python:3.11-slim-bookworm

WORKDIR /app

# 1. Install system dependencies
# These are required for Pillow, lxml, and grpcio to compile correctly
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    libffi-dev \
    libssl-dev \
    pkg-config \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libjpeg-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Python Dependencies via pip (System-wide)
COPY requirements.txt .

# IMPORTANT: We do NOT upgrade pip here. 
# The default pip (v24.0) works fine. Upgrading to pip v25.3 crashes 
# on Docker Desktop because it can't parse the 'linuxkit' kernel version.
RUN pip install --no-cache-dir -r requirements.txt

# 3. Install Playwright Browsers
# This installs directly to the system location since we aren't using a venv
RUN playwright install --with-deps chromium

COPY . .
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]