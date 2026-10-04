from pyspark import pipelines as dp
from pyspark.sql.functions import col, explode, expr, from_json, regexp_replace, to_timestamp
from pyspark.sql.types import ArrayType, StringType, StructField, StructType

# Bronze keeps `events` as a JSON string (Auto Loader reads JSON fields as text
# by default), so Silver parses it with an explicit schema.
TICKER_SCHEMA = StructType(
    [
        StructField(name, StringType())
        for name in [
            "type",
            "product_id",
            "price",
            "volume_24_h",
            "low_24_h",
            "high_24_h",
            "low_52_w",
            "high_52_w",
            "price_percent_chg_24_h",
            "best_bid",
            "best_ask",
            "best_bid_quantity",
            "best_ask_quantity",
        ]
    ]
)
EVENTS_SCHEMA = ArrayType(
    StructType(
        [
            StructField("type", StringType()),
            StructField("tickers", ArrayType(TICKER_SCHEMA)),
        ]
    )
)


def to_decimal(name, precision=18, scale=8):
    return expr(f"try_cast({name} as decimal({precision},{scale}))")


@dp.table(
    name="workspace.silver.coinbase_ticker",
    table_properties={"quality": "silver"}
)
@dp.expect_all_or_drop({
    "event_time_not_null": "event_time IS NOT NULL",
    "product_id_not_null": "product_id IS NOT NULL",
    "price_positive": "price > 0",
    "bid_not_above_ask": "best_bid <= best_ask",
})
def coinbase_ticker():
    return (
        dp.read_stream("coinbase_bronze")
        .where(col("channel") == "ticker")
        .select(
            col("sequence_num").cast("bigint").alias("sequence_num"),
            # Coinbase sends nanoseconds; Spark timestamps hold microseconds.
            to_timestamp(
                regexp_replace(col("timestamp"), r"(\.\d{6})\d*Z$", "$1Z")
            ).alias("event_time"),
            explode(from_json(col("events"), EVENTS_SCHEMA)).alias("event"),
            col("ingestion_timestamp"),
            col("source_file"),
        )
        .select(
            "event_time",
            "sequence_num",
            col("event.type").alias("event_type"),
            explode(col("event.tickers")).alias("ticker"),
            "ingestion_timestamp",
            "source_file",
        )
        .select(
            col("ticker.product_id").alias("product_id"),
            "event_time",
            "sequence_num",
            "event_type",
            to_decimal("ticker.price").alias("price"),
            to_decimal("ticker.best_bid").alias("best_bid"),
            to_decimal("ticker.best_ask").alias("best_ask"),
            to_decimal("ticker.best_bid_quantity").alias("best_bid_quantity"),
            to_decimal("ticker.best_ask_quantity").alias("best_ask_quantity"),
            to_decimal("ticker.volume_24_h", 24, 8).alias("volume_24h"),
            to_decimal("ticker.high_24_h").alias("high_24h"),
            to_decimal("ticker.low_24_h").alias("low_24h"),
            to_decimal("ticker.high_52_w").alias("high_52w"),
            to_decimal("ticker.low_52_w").alias("low_52w"),
            to_decimal("ticker.price_percent_chg_24_h", 18, 12).alias("price_pct_chg_24h"),
            "ingestion_timestamp",
            "source_file",
        )
        # sequence_num restarts when the consumer reconnects, so the key
        # includes the event time as well.
        .withWatermark("event_time", "1 hour")
        .dropDuplicatesWithinWatermark(["product_id", "event_time", "sequence_num"])
    )
