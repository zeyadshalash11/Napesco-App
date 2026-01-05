# Dockerfile for Napesco App on Railway (Final Version v3)

# 1. Start from an official Python image
FROM python:3.12-slim-bookworm

# 2. Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# --- THIS IS THE FIX ---
# Set a dummy SECRET_KEY that is ONLY used during the build process.
# This allows collectstatic to run without crashing.
ENV SECRET_KEY=dummy-build-secret-key

# 3. Install WeasyPrint's system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    python3-cffi \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 4. Set the working directory
WORKDIR /app

# 5. Install Python libraries
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of the application code
COPY . /app/

# 7. Run collectstatic
RUN python manage.py collectstatic --noinput

# 8. Define the command to run the application
# The real SECRET_KEY from the Railway UI will be used here.
CMD ["gunicorn", "napesco_portal.wsgi", "--bind", "0.0.0.0:$PORT"]