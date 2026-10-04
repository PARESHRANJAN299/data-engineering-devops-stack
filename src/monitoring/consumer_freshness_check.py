"""Fail when the Coinbase consumer has stopped writing files to S3.

The consumer flushes a batch roughly every 15 seconds, so a newest raw file that
is much older than that means the EC2 consumer is down (or cannot reach S3).
This check reads S3 directly, so it does not depend on the Bronze pipeline.
"""
import sys
from datetime import datetime, timedelta, timezone

from pyspark.sql import SparkSession
from pyspark.sql.functions import max as spark_max

RAW_PATH = "s3://paresh-data-engineering-coinbase-dev/coinbase/raw"
MAX_AGE_MINUTES = 10

spark = SparkSession.builder.getOrCreate()
now = datetime.now(timezone.utc)

latest = None
for day in (now, now - timedelta(days=1)):
    path = f"{RAW_PATH}/{day:%Y/%m/%d}/"
    try:
        row = (
            spark.read.format("binaryFile")
            .option("pathGlobFilter", "*.json")
            .option("recursiveFileLookup", "true")
            .load(path)
            .select(spark_max("modificationTime"))
            .first()
        )
    except Exception as exc:  # folder does not exist yet
        print(f"No files under {path}: {type(exc).__name__}")
        continue
    if row[0] is not None and (latest is None or row[0] > latest):
        latest = row[0]

if latest is None:
    print("ALERT: no Coinbase raw files found for today or yesterday.")
    sys.exit(1)

latest = latest.replace(tzinfo=timezone.utc) if latest.tzinfo is None else latest
age = now - latest
print(f"Newest raw file: {latest.isoformat()} ({age.total_seconds() / 60:.1f} minutes ago)")

if age > timedelta(minutes=MAX_AGE_MINUTES):
    print(
        f"ALERT: the Coinbase consumer looks stopped. No new file for more than "
        f"{MAX_AGE_MINUTES} minutes."
    )
    sys.exit(1)

print("OK: consumer is writing fresh data.")
