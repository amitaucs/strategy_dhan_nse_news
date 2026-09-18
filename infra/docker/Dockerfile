# Production Dockerfile for Unified NSE Trading Platform
# Packages News Catalyst Strategy, ST-14 Bullish CE Options, and Scanner Dhan
FROM python:3.11-slim

# Prevent python from writing pyc files and buffering stdout/stderr; configure IST timezone
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app/scanners/scanner_dhan/src:/app/strategies/st14_bullish_ce/src \
    TZ=Asia/Kolkata

WORKDIR /app

# Install system dependencies (curl for healthchecks, tzdata for Indian Standard Time)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies first to leverage Docker layer caching
COPY strategies/news_based_strategy/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code, scanners package, and universe data
COPY strategies/news_based_strategy/src/ ./src/
COPY strategies/news_based_strategy/data/ ./data/
COPY scanners/ ./scanners/
COPY strategies/st14_bullish_ce/ ./strategies/st14_bullish_ce/

# Ensure data directory exists for persistent SQLite database and runtime files
RUN mkdir -p /app/data

# Default expose port for web dashboard
EXPOSE 8000

# Health check to verify web server availability
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/status || exit 1

# Default command: Launch interactive Web GUI terminal
CMD ["python3", "-m", "news_based_strategy.main", "--gui", "--host", "0.0.0.0", "--port", "8000"]

