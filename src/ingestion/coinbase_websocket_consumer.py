import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import websocket
from botocore.config import Config

PRODUCT_ID = "BTC-USD"
BUFFER_SECONDS = 15

WS_URL = "wss://advanced-trade-ws.coinbase.com"

S3_BUCKET = "paresh-data-engineering-coinbase-dev"
S3_PREFIX = "coinbase/raw"

UPLOAD_ATTEMPTS = 5
MAX_BUFFER_EVENTS = 50_000
SPOOL_DIR = Path("/var/tmp/coinbase_spool")

RECONNECT_MIN_SECONDS = 1
RECONNECT_MAX_SECONDS = 60
STABLE_CONNECTION_SECONDS = 60

s3 = boto3.client("s3", config=Config(retries={"max_attempts": 5, "mode": "standard"}))

event_buffer = []
last_flush_time = time.time()
shutting_down = False


def build_key(now):
    return f"{S3_PREFIX}/{now:%Y/%m/%d/%H}/events_{now:%Y%m%d_%H%M%S_%f}.json"


def upload(key, body):
    """Upload one object, retrying with backoff. Returns True on success."""
    for attempt in range(1, UPLOAD_ATTEMPTS + 1):
        try:
            s3.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=body,
                ContentType="application/json",
            )
            return True
        except Exception as error:
            print(f"S3 upload failed (attempt {attempt}/{UPLOAD_ATTEMPTS}): {error}")
            if attempt < UPLOAD_ATTEMPTS:
                time.sleep(2**attempt)
    return False


def spool_batch(key, body):
    """Keep a batch on local disk when S3 stays unreachable."""
    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    spool_file = SPOOL_DIR / key.replace("/", "__")
    spool_file.write_bytes(body)
    print(f"Spooled batch to {spool_file}")


def upload_spooled_batches():
    """Upload batches saved on disk by an earlier failed flush."""
    if not SPOOL_DIR.exists():
        return
    for spool_file in sorted(SPOOL_DIR.iterdir()):
        key = spool_file.name.replace("__", "/")
        if upload(key, spool_file.read_bytes()):
            spool_file.unlink()
            print(f"Uploaded spooled batch to s3://{S3_BUCKET}/{key}")
        else:
            print(f"Spooled batch {spool_file} still not uploaded; will retry later")
            return


def flush_buffer():
    global event_buffer, last_flush_time

    last_flush_time = time.time()

    if not event_buffer:
        return

    now = datetime.now(timezone.utc)
    key = build_key(now)
    body = "\n".join(json.dumps(event) for event in event_buffer).encode("utf-8")

    if upload(key, body):
        print(f"Wrote {len(event_buffer)} events to s3://{S3_BUCKET}/{key}")
        event_buffer = []
        upload_spooled_batches()
        return

    # All retries failed: move the batch to disk so the buffer cannot grow forever.
    spool_batch(key, body)
    event_buffer = []


def on_open(ws):
    print("Connected to Coinbase WebSocket")

    subscribe_message = {
        "type": "subscribe",
        "channel": "ticker",
        "product_ids": [PRODUCT_ID],
    }

    ws.send(json.dumps(subscribe_message))
    print(f"Subscribed to {PRODUCT_ID}")


def on_message(ws, message):
    event = json.loads(message)

    if event.get("channel") == "ticker":
        event_buffer.append(event)
        if len(event_buffer) > MAX_BUFFER_EVENTS:
            del event_buffer[0]

    if time.time() - last_flush_time >= BUFFER_SECONDS:
        flush_buffer()


def on_error(ws, error):
    print(f"WebSocket error: {error}")


def on_close(ws, close_status_code, close_msg):
    flush_buffer()
    print(f"WebSocket connection closed ({close_status_code} {close_msg})")


def handle_stop_signal(signum, frame):
    global shutting_down
    shutting_down = True
    print(f"Received signal {signum}; flushing and stopping")
    raise KeyboardInterrupt


def run():
    signal.signal(signal.SIGTERM, handle_stop_signal)

    print("Coinbase WebSocket consumer starting...")
    print(f"Product: {PRODUCT_ID}")
    print(f"Buffer window: {BUFFER_SECONDS} seconds")

    upload_spooled_batches()

    delay = RECONNECT_MIN_SECONDS
    try:
        while not shutting_down:
            ws = websocket.WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            connected_at = time.time()
            # ping/pong detects a connection that is silently dead.
            ws.run_forever(ping_interval=20, ping_timeout=10)

            if shutting_down:
                break

            # A connection that lasted a while resets the backoff.
            if time.time() - connected_at >= STABLE_CONNECTION_SECONDS:
                delay = RECONNECT_MIN_SECONDS
            print(f"Disconnected; reconnecting in {delay} seconds")
            time.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        flush_buffer()
        print("Consumer stopped")


if __name__ == "__main__":
    run()
    sys.exit(0)
