# Dockerfile for CouchDB Manager
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
# Install, then drop the packaging tools (not needed at runtime; their vendored libraries carry CVEs)
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y setuptools wheel pip

# Copy application files
COPY couchdb_manager.py .
COPY manage/ ./manage/

# Make shell script executable, run as a non-root user owning the backups directory
RUN chmod +x manage/backup_restore_couchdb.sh \
    && useradd --uid 1000 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p backups && chown app:app backups
USER app

# Expose Streamlit default port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run the application
CMD ["streamlit", "run", "couchdb_manager.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]