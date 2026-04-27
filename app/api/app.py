import os
import string
import random
import logging

import pika
import psycopg2
import redis as redis_lib
from flask import Flask, jsonify, redirect, request
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

# Configure logging so every request and error shows up in docker compose logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Read all credentials from environment variables — never hardcode them.
# These will be injected by Docker Compose from the .env file.
DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ["DB_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASS = os.environ["DB_PASS"]

REDIS_HOST = os.environ["REDIS_HOST"]
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")

RABBITMQ_HOST = os.environ["RABBITMQ_HOST"]
RABBITMQ_USER = os.environ["RABBITMQ_USER"]
RABBITMQ_PASS = os.environ["RABBITMQ_PASS"]

BASE_URL = os.environ.get("BASE_URL", "http://localhost")

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

# Counters only increase. Prometheus computes rates from the totals.
SHORTEN_COUNTER = Counter("urlshortener_shorten_total", "Total URLs shortened")
REDIRECT_COUNTER = Counter(
    "urlshortener_redirect_total", "Total redirects served"
)
CACHE_HIT_COUNTER = Counter(
    "urlshortener_cache_hits_total", "Redis cache hits"
)
CACHE_MISS_COUNTER = Counter(
    "urlshortener_cache_misses_total", "Redis cache misses"
)

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def get_db():
    """Open a new Postgres connection. Called per-request; closed after use."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def get_redis():
    """Return a Redis client. The client is thread-safe and can be reused."""
    return redis_lib.Redis(
        host=REDIS_HOST, port=int(REDIS_PORT), decode_responses=True
    )


def init_db():
    """
    Create tables if they don't already exist.
    Called once at startup. Safe to run multiple times (idempotent).
    """
    conn = get_db()
    cur = conn.cursor()
    # The urls table maps short codes to long URLs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS urls (
            id SERIAL PRIMARY KEY,
            short_code VARCHAR(10) UNIQUE NOT NULL,
            long_url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    # The analytics table is written to by the worker, not the API
    cur.execute("""
        CREATE TABLE IF NOT EXISTS analytics (
            id SERIAL PRIMARY KEY,
            short_code VARCHAR(10) NOT NULL,
            clicked_at TIMESTAMP DEFAULT NOW(),
            ip_address VARCHAR(45)
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    logger.info("Database initialised.")


# ---------------------------------------------------------------------------
# Short code generation
# ---------------------------------------------------------------------------

def generate_short_code(length=6):
    """Return a random alphanumeric string of `length` characters."""
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=length))


def publish_click_event(short_code: str, ip: str):
    """
    Send a click event to RabbitMQ so the worker can record it asynchronously.
    Fire-and-forget: if RabbitMQ is down we log and move on rather than
    failing the redirect. The user still gets their redirect.
    """
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        params = pika.ConnectionParameters(
            host=RABBITMQ_HOST, credentials=credentials
        )
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        # Declaring here is safe — queue_declare is idempotent.
        channel.queue_declare(queue="click_events", durable=True)
        channel.basic_publish(
            exchange="",
            routing_key="click_events",
            body=f"{short_code}:{ip}",
            # Make the message persistent so it survives a RabbitMQ restart
            properties=pika.BasicProperties(delivery_mode=2),
        )
        connection.close()
    except Exception as e:
        logger.warning("Could not publish click event to RabbitMQ: %s", e)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    """
    Liveness check. Docker Compose and Kubernetes both poll this.
    Returns 200 as long as the process is running — does not check deps.
    """
    return jsonify({"status": "ok"}), 200


@app.route("/metrics")
def metrics():
    """Expose Prometheus metrics. Scraped by Prometheus in Phase 5."""
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/shorten", methods=["POST"])
def shorten():
    """
    Accept a JSON body: {"url": "https://example.com/very/long/path"}
    Return: {"short_url": "http://localhost/aB3xYz"}
    """
    data = request.get_json(silent=True)
    if not data or "url" not in data:
        return jsonify({"error": "JSON body must contain a 'url' field"}), 400

    long_url = data["url"].strip()
    if not long_url.startswith(("http://", "https://")):
        return jsonify({"error": "URL must use http or https"}), 400

    # Generate a unique short code. Retry on the rare collision.
    conn = get_db()
    cur = conn.cursor()
    for _ in range(5):
        code = generate_short_code()
        cur.execute("SELECT 1 FROM urls WHERE short_code = %s", (code,))
        if cur.fetchone() is None:
            break
    else:
        cur.close()
        conn.close()
        return jsonify({"error": "Failed to generate unique code"}), 500

    cur.execute(
        "INSERT INTO urls (short_code, long_url) VALUES (%s, %s)",
        (code, long_url),
    )
    conn.commit()
    cur.close()
    conn.close()

    SHORTEN_COUNTER.inc()
    short_url = f"{BASE_URL}/{code}"
    logger.info("Shortened %s → %s", long_url, short_url)
    return jsonify({"short_url": short_url, "code": code}), 201


@app.route("/<short_code>")
def redirect_to_long(short_code):
    """
    Look up the short code and redirect to the original URL.
    Check Redis first (fast cache), then Postgres (source of truth).
    """
    r = get_redis()

    # --- Cache hit path ---
    long_url = r.get(f"url:{short_code}")
    if long_url:
        CACHE_HIT_COUNTER.inc()
        REDIRECT_COUNTER.inc()
        publish_click_event(short_code, request.remote_addr or "unknown")
        return redirect(long_url, code=302)

    # --- Cache miss path: query Postgres, then populate cache ---
    CACHE_MISS_COUNTER.inc()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT long_url FROM urls WHERE short_code = %s", (short_code,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row is None:
        return jsonify({"error": "Short code not found"}), 404

    long_url = row[0]
    # Cache for 1 hour (3600 seconds). EX sets an expiry time.
    r.set(f"url:{short_code}", long_url, ex=3600)

    REDIRECT_COUNTER.inc()
    publish_click_event(short_code, request.remote_addr or "unknown")
    return redirect(long_url, code=302)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

# Called at module load so it runs under gunicorn (import) and flask run.
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
