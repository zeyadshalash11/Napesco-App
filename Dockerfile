# Dockerfile for Napesco App on Railway

# 1. Start from an official, full-featured Python image
FROM python:3.12-slim-bookworm

# 2. Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Install WeasyPrint's system dependencies
# This is the most important part. We use apt-get to install everything.
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    python3-cffi \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 4. Set the working directory inside the container
WORKDIR /app

# 5. Copy the requirements file and install Python libraries
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of the application code
COPY . /app/

# 7. Expose the port that Gunicorn will run on (Railway will map this)
EXPOSE 8000