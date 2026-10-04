import json
import time
from datetime import datetime, timezone

import boto3
import websocket

PRODUCT_ID = "BTC-USD"
BUFFER_SECONDS = 15

WS_URL = "wss://advanced-trade-ws.coinbase.com"

S3_BUCKET = "paresh-data-engineering-coinbase-dev"
S3_PREFIX = "coinbase/raw"

s3 = boto3.client("s3")

event_buffer = []
last_flush_time = time.time()


def flush_buffer():
    global event_buffer, last_flush_time

    if not event_buffer:
        return

    now = datetime.now(timezone.utc)

    key = (
        f"{S3_PREFIX}/"
        f"{now:%Y/%m/%d/%H}/"
        f"events_{now:%Y%m%d_%H%M%S}.json"
    )

    body = "\n".join(json.dumps(event) for event in event_buffer)

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType="application/json",
    )

    print(f"Wrote {len(event_buffer)} events to s3://{S3_BUCKET}/{key}")

    event_buffer = []
    last_flush_time = time.time()


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
    global last_flush_time

    event = json.loads(message)

    if event.get("channel") == "ticker":
        event_buffer.append(event)

    if time.time() - last_flush_time >= BUFFER_SECONDS:
        flush_buffer()


def on_error(ws, error):
    print(f"WebSocket error: {error}")


def on_close(ws, close_status_code, close_msg):
    flush_buffer()
    print("WebSocket connection closed")


print("Coinbase WebSocket consumer starting...")
print(f"Product: {PRODUCT_ID}")
print(f"Buffer window: {BUFFER_SECONDS} seconds")

ws = websocket.WebSocketApp(
    WS_URL,
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close,
)

ws.run_forever()