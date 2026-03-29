FROM python:3.11-slim

WORKDIR /app

# System deps for Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgtk-3-0 && \
    rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files first (layer caching)
COPY pyproject.toml ./
RUN uv sync --no-dev

# Install Playwright Chromium
RUN uv run playwright install chromium

# Copy app source
COPY . .

# Create data directory
RUN mkdir -p data

EXPOSE 8000

CMD ["uv", "run", "python", "run.py"]
