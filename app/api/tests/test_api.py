import os
import json
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Bootstrap — must happen before importing app.py
# ---------------------------------------------------------------------------

# app.py reads these from os.environ at import time. Set them before the import
# so the module doesn't raise KeyError.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_NAME", "testdb")
os.environ.setdefault("DB_USER", "testuser")
os.environ.setdefault("DB_PASS", "testpass")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("RABBITMQ_HOST", "localhost")
os.environ.setdefault("RABBITMQ_USER", "guest")
os.environ.setdefault("RABBITMQ_PASS", "guest")
os.environ.setdefault("BASE_URL", "http://localhost")

# app.py calls init_db() at module level, opening a real Postgres connection.
# Patch psycopg2.connect before the import so that call becomes a no-op.
with patch("psycopg2.connect"):
    from app import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_cursor(fetchone_return=None):
    """Return a mock DB cursor. fetchone() returns the given value."""
    cur = MagicMock()
    cur.fetchone.return_value = fetchone_return
    return cur


def make_conn(cursor):
    """Return a mock DB connection that yields the given cursor."""
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# POST /shorten
# ---------------------------------------------------------------------------


@patch("app.publish_click_event")
@patch("app.get_redis")
@patch("app.get_db")
def test_shorten_valid_url(mock_get_db, mock_get_redis, mock_publish, client):
    # fetchone returns None → no short code collision found → INSERT proceeds
    mock_get_db.return_value = make_conn(make_cursor(fetchone_return=None))

    response = client.post(
        "/shorten",
        data=json.dumps({"url": "https://example.com/very/long/path"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.get_json()
    assert "short_url" in body
    assert body["short_url"].startswith("http://localhost/")


@patch("app.get_db")
def test_shorten_missing_url_field(mock_get_db, client):
    response = client.post(
        "/shorten",
        data=json.dumps({"not_url": "https://example.com"}),
        content_type="application/json",
    )
    assert response.status_code == 400


@patch("app.get_db")
def test_shorten_invalid_url(mock_get_db, client):
    # URL that doesn't start with http:// or https://
    response = client.post(
        "/shorten",
        data=json.dumps({"url": "not-a-valid-url"}),
        content_type="application/json",
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /<short_code>
# ---------------------------------------------------------------------------


@patch("app.publish_click_event")
@patch("app.get_redis")
@patch("app.get_db")
def test_redirect_cache_miss(
        mock_get_db, mock_get_redis, mock_publish, client):
    # Redis returns None (cache miss) → fall through to Postgres
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_get_redis.return_value = mock_redis

    mock_get_db.return_value = make_conn(
        make_cursor(fetchone_return=("https://example.com",))
    )

    response = client.get("/abc123")

    assert response.status_code == 302
    assert response.headers["Location"] == "https://example.com"


@patch("app.publish_click_event")
@patch("app.get_redis")
def test_redirect_cache_hit(mock_get_redis, mock_publish, client):
    # Redis returns the URL directly → Postgres is never consulted
    mock_redis = MagicMock()
    mock_redis.get.return_value = "https://example.com"
    mock_get_redis.return_value = mock_redis

    response = client.get("/abc123")

    assert response.status_code == 302
    assert response.headers["Location"] == "https://example.com"


@patch("app.get_redis")
@patch("app.get_db")
def test_redirect_missing_code(mock_get_db, mock_get_redis, client):
    # Both Redis and Postgres return nothing → 404
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_get_redis.return_value = mock_redis

    mock_get_db.return_value = make_conn(make_cursor(fetchone_return=None))

    response = client.get("/doesnotexist")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
