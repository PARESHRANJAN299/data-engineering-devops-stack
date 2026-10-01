from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp, input_file_name

spark = SparkSession.builder.getOrCreate()

raw_path = "s3://paresh-data-engineering-coinbase-dev/coinbase/raw/"

bronze_df = (
    spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "json")
    .load(raw_path)
    .withColumn("ingestion_timestamp", current_timestamp())
    .withColumn("source_file", input_file_name())
)

(
    bronze_df.writeStream
    .format("delta")
    .option(
        "checkpointLocation",
        "/tmp/checkpoints/coinbase_bronze"
    )
    .outputMode("append")
    .toTable("coinbase_bronze")
)
