# Tele-Agent Dockerfile
# Clean image - personality files are mounted at runtime
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code only
COPY src/ ./src/
COPY skills/ ./skills/

# Create directories for runtime mounts
RUN mkdir -p /app/data /app/personality /app/logs

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default paths for container
ENV SKILLS_DIR=/app/skills
ENV CHROMA_PERSIST_DIR=/app/data/chroma
ENV STATE_FILE=/app/data/state.json

# Personality files are expected to be mounted at /app/personality/
# Mount: SOUL.md, IDENTITY.md, USER.md, TOOLS.md

# Health check - ensures container is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Run the bot
CMD ["python", "-m", "src.main"]
