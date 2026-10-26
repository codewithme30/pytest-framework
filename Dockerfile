# ---------------------------------------------------------------------------
# Author  : Anil Kalisetti
# Purpose : Reproducible test runner: identical Python, Chromium and dependencies everywhere.
# Build   : docker build -t pytest-framework .
# Run     : docker run --rm -v "$PWD/reports:/app/reports" pytest-framework -m "not ui"
# ---------------------------------------------------------------------------
FROM python:3.12-slim

# Chromium + matching driver from Debian so UI tests also run fully offline from browser CDNs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CHROME_BINARY=/usr/bin/chromium \
    HEADLESS=true

WORKDIR /app

# Dependencies first: this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run as an unprivileged user (the reports folder must be writable).
RUN useradd --create-home runner && mkdir -p reports && chown -R runner /app
USER runner

ENTRYPOINT ["pytest"]
CMD ["-m", "not slow"]
