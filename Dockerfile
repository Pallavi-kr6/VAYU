# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# System dependencies for geospatial + ML
RUN apt-get update && apt-get install -y \
    gcc g++ libgeos-dev libproj-dev \
    libpq-dev curl git && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Make run script executable
RUN chmod +x scripts/run_demo.sh

# Create model/data dirs
RUN mkdir -p models/saved data/raw data/processed logs

EXPOSE 8000 8501

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
