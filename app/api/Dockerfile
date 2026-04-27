# =============================================================================
# Stage 1 — builder
# Install dependencies into a separate layer we can copy from.
# This stage never ends up in the final image.
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

# Copy only the requirements file first. Docker caches this layer — if
# requirements.txt hasn't changed, pip install is skipped on the next build.
COPY requirements.txt .

RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# =============================================================================
# Stage 2 — runtime
# Start from the same slim base. Copy only the installed packages from builder.
# =============================================================================
FROM python:3.12-slim

# Run as a non-root user — if the process is compromised, the attacker
# doesn't get root inside the container.
RUN useradd --create-home appuser
USER appuser
WORKDIR /app

# Copy installed packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application code
COPY app.py .

EXPOSE 5000

# gunicorn is a production-grade WSGI server; flask's built-in server is
# single-threaded and not safe for production.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
