# COD Commerce Platform Backend
# Single FastAPI container for Koyeb deployment

# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ backend/
COPY prisma/ prisma/

# Generate Prisma client
RUN prisma generate

# Download and validate GeoLite2 database at build time
# This ensures the database is bundled into the image
# In production, this would download from MaxMind using a license key
# Database is optional for build; will be downloaded at runtime if needed
# COPY backend/GeoLite2-Country.mmdb /app/GeoLite2-Country.mmdb || true

# Expose port
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
