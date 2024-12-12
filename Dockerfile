FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Expose port for API
EXPOSE 8000

# Use environment variable to determine which service to run
ENV SERVICE_TYPE=sync

CMD if [ "$SERVICE_TYPE" = "api" ]; then \
        python api_service.py; \
    else \
        python main.py; \
    fi
