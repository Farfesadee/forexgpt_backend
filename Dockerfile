# ============================================================
# Dockerfile — ForexGPT Backend
# Base: Python 3.12 slim (matches your local Python 3.12.7)
# ============================================================

FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# ── System dependencies ──────────────────────────────────────
# gcc and build-essential are needed for some pip packages
# (numpy, pandas, cryptography)
RUN apt-get update && apt-get install -y \
    gcc \
    build-essential \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Install Python dependencies ──────────────────────────────
# Copy requirements first so Docker caches this layer
# Only re-runs pip install if requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Copy project files ───────────────────────────────────────
# Copy all application code into the container
COPY api/          ./api/
COPY backtesting/  ./backtesting/
COPY core/         ./core/
COPY data/         ./data/
COPY models/       ./models/
COPY prompts/      ./prompts/
COPY routes/       ./routes/
COPY services/     ./services/
COPY supabase_project/     ./supabase_project/
COPY main.py       .

# ── Create non-root user for security ────────────────────────
# Running as root inside a container is a security risk
RUN adduser --disabled-password --gecos "" forexgpt \
    && chown -R forexgpt:forexgpt /app
USER forexgpt

# ── Expose port ──────────────────────────────────────────────
EXPOSE 8000

# ── Health check ─────────────────────────────────────────────
# Docker checks this every 30s to know if container is healthy
# Note: /health endpoint requires JWT so we check the docs page
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

# ── Start command ─────────────────────────────────────────────
# workers=2 is safe for a single-core VPS
# timeout-keep-alive matches your existing uvicorn setting
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--timeout-keep-alive", "120"]
