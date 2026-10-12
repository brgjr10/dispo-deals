FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for cloudscraper and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data and cache directories
RUN mkdir -p /app/data /app/cache/images

# Expose port for API server
EXPOSE 4040

# Default command runs the scraper once (override in docker-compose)
CMD ["python", "main.py", "--once"]