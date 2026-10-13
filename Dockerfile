FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for cloudscraper and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data and cache directories with proper ownership
RUN mkdir -p /app/data /app/cache/images && chown -R appuser:appuser /app/data /app/cache

# Switch to non-root user
USER appuser

# Expose port for API server
EXPOSE 4040

# Health check for container monitoring
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:4040/api/data || exit 1

# Default command runs the scraper once (override in docker-compose)
CMD ["python", "main.py", "--once"]