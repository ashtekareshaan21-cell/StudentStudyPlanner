# ==========================================
# STAGE 1: Build Dependencies
# ==========================================
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install dependencies to a user-level directory
RUN pip install --no-cache-dir --user -r requirements.txt

# ==========================================
# STAGE 2: Production Runtime
# ==========================================
FROM python:3.11-slim AS runner

WORKDIR /app

# Create a non-privileged user and group for running the app
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Copy installed python dependencies from the builder stage
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY . .

# Ensure the appuser has ownership of the /app directory
RUN chown -R appuser:appgroup /app

# Add the local bin path to the runner user's environment PATH
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Switch to the non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 5000

# Run with Gunicorn on startup, binding dynamically to Render's exposed $PORT env var (falling back to 5000)
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 4 --threads 2 --timeout 60 app:app"]
