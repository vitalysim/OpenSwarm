FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    VIRTUAL_ENV=/app/.venv


# Keep a deterministic PATH (avoid `${PATH}` evaluation issues in some BuildKit setups).
ENV PATH=/app/.venv/bin:/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Install system dependencies for:
# - Node.js (for html2pptx)
# - LibreOffice (for thumbnail/PDF conversion)
# - Poppler (for pdftoppm)
# - Playwright browser dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    # Node.js
    curl \
    # LibreOffice for PDF conversion
    libreoffice-impress \
    # Poppler for pdftoppm
    poppler-utils \
    # Playwright Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    # Clean up
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 LTS
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements first for layer caching
COPY requirements.txt .
RUN uv venv "$VIRTUAL_ENV" && \
    uv pip install --python "$VIRTUAL_ENV/bin/python" --no-cache -r requirements.txt

# Copy Node.js package files and patches before install so patch-package can apply them
COPY package.json package-lock.json* ./
COPY patches/ patches/
RUN npm ci || npm install

# Create output directories
RUN mkdir -p /app/activity-logs \
    /app/mnt && \
    chmod -R a+rwx /app/activity-logs /app/mnt

# Copy the rest of the application
COPY . .

CMD python -u server.py
