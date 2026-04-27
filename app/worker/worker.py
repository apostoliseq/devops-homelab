import os
import time
import logging
import psycopg2
import pika

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# All credentials come from environment variables, same as the API.
DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ["DB_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASS = os.environ["DB_PASS"]

RABBITMQ_HOST = os.environ["RABBITMQ_HOST"]
RABBITMQ_USER = os.environ["RABBITMQ_USER"]
RABBITMQ_PASS = os.environ["RABBITMQ_PASS"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_db():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def record_click(short_code: str, ip: str):
    """Write one row to the analytics table."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO analytics (short_code, ip_address) VALUES (%s, %s)",
        (short_code, ip),
    )
    conn.commit()
    cur.close()
    conn.close()

# ---------------------------------------------------------------------------
# RabbitMQ consumer
# ---------------------------------------------------------------------------


def on_message(channel, method, properties, body):
    """
    Called once per message. body is bytes: b"short_code:ip_address"
    We split on ':' and write to Postgres.
    """
    try:
        text = body.decode()
        # The API publishes "short_code:ip" — split on the first colon only
        short_code, ip = text.split(":", 1)
        record_click(short_code, ip)
        logger.info("Recorded click: %s from %s", short_code, ip)
        # Acknowledge the message so RabbitMQ removes it from the queue.
        # Without this, the message is re-delivered on worker restart.
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error("Failed to process message %r: %s", body, e)
        # Negative-acknowledge and re-queue so we don't silently drop the event
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def connect_with_retry(max_attempts=10, delay=5):
    """
    RabbitMQ takes several seconds to start. This loop retries the connection
    so the worker doesn't crash when it boots before RabbitMQ is ready.
    """
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST, credentials=credentials
    )

    for attempt in range(1, max_attempts + 1):
        try:
            connection = pika.BlockingConnection(params)
            logger.info("Connected to RabbitMQ on attempt %d", attempt)
            return connection
        except pika.exceptions.AMQPConnectionError as e:
            logger.warning("Attempt %d/%d failed: %s. Retrying in %ds...",
                           attempt, max_attempts, e, delay)
            time.sleep(delay)

    raise RuntimeError(
        "Could not connect to RabbitMQ after %d attempts" % max_attempts
    )

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    connection = connect_with_retry()
    channel = connection.channel()

    # Durable=True means the queue survives a RabbitMQ restart.
    channel.queue_declare(queue="click_events", durable=True)

    # Only fetch one message at a time — don't overwhelm the worker
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="click_events", on_message_callback=on_message)

    logger.info("Worker started. Waiting for click events...")
    # This blocks forever, calling on_message each time a message arrives.
    channel.start_consuming()


if __name__ == "__main__":
    main()
