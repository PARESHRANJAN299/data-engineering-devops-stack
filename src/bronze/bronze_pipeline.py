from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

df = spark.range(1, 6)

df.write.mode("overwrite").format("delta").saveAsTable("bronze_demo_table")
