from pyspark import pipelines as dp
from pyspark.sql.functions import current_timestamp, input_file_name

raw_path = "s3://paresh-data-engineering-coinbase-dev/coinbase/raw/"

@dp.table(
    name="coinbase_bronze",
    table_properties={"quality": "bronze"}
)
def coinbase_bronze():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load(raw_path)
        .withColumn("ingestion_timestamp", current_timestamp())
        .withColumn("source_file", input_file_name())
    )