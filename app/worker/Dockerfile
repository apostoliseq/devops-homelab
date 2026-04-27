# =============================================================================
# Stage 1 — builder
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .

RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# =============================================================================
# Stage 2 — runtime
# =============================================================================
FROM python:3.12-slim

RUN useradd --create-home appuser
USER appuser
WORKDIR /app

COPY --from=builder /install /usr/local

COPY worker.py .

# The worker is a long-running consumer loop — it has no HTTP port to expose.
CMD ["python", "worker.py"]
