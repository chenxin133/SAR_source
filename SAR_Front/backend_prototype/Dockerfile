FROM python:3.11-slim

# Install system dependencies for GDAL and Pillow-SIMD
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libjpeg-dev \
    zlib1g-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for GDAL
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

WORKDIR /app

COPY requirements.txt .

# Install Python dependencies
# Note: Pillow-SIMD usually needs to be installed with --no-binary :all: or compiled from source for SIMD support
# But for simplicity in Dockerfile we just pip install. 
# For GDAL python bindings, we match the system GDAL version.
RUN pip install --no-cache-dir -r requirements.txt

# Re-install Pillow-SIMD to ensure it uses system libjpeg
RUN pip uninstall -y pillow && \
    pip install --no-cache-dir --force-reinstall --no-binary :all: Pillow-SIMD

COPY . .

# Create directories
RUN mkdir -p uploads thumbnails

# Expose port
EXPOSE 8000

# Start script
# We run both worker and web server for demo purposes. 
# In production, these should be separate containers.
CMD celery -A tasks worker --loglevel=info --concurrency=2 & \
    uvicorn main:app --host 0.0.0.0 --port 8000
