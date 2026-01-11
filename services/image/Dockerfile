FROM python:3.11-slim

# Install system dependencies including image processing tools
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libtiff5-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user (no recursive chown)
RUN useradd -m -u 1000 appuser

# Copy shared modules (set owner during copy)
COPY --chown=1000:1000 shared/ ./shared/

# Copy service code (set owner during copy)
COPY --chown=1000:1000 services/image/ ./

USER appuser

# Expose port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002", "--reload"]
