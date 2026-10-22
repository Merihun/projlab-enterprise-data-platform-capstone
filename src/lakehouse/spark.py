"""Spark session helpers for local-mode PySpark + Delta Lake."""

from __future__ import annotations

import os

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession

# Spark 3.5 is built against Hadoop 3.3.4; hadoop-aws must match it exactly.
HADOOP_AWS = "org.apache.hadoop:hadoop-aws:3.3.4"


def get_spark(app_name: str = "projlab", *, s3: bool = False) -> SparkSession:
    """Create (or reuse) a local Spark session with Delta Lake enabled.

    With ``s3=True`` the session can also read and write ``s3a://<bucket>/...`` on the lab's object
    storage. The first such session downloads hadoop-aws and the AWS SDK bundle (~300 MB).
    Spark packages are loaded once per Python process: if this process already started Spark without
    ``s3=True`` (for example earlier in the same notebook), restart the kernel first.
    """
    builder = (
        SparkSession.builder.appName(app_name)
        .master(os.environ.get("SPARK_MASTER", "local[*]"))
        .config("spark.driver.memory", os.environ.get("SPARK_DRIVER_MEMORY", "2g"))
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.ui.showConsoleProgress", "false")
    )
    extra_packages: list[str] = []
    if s3:
        extra_packages.append(HADOOP_AWS)
        builder = (
            builder.config("spark.hadoop.fs.s3a.endpoint", os.environ["S3_ENDPOINT_URL"])
            .config("spark.hadoop.fs.s3a.path.style.access", "true")
            .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
            .config("spark.hadoop.fs.s3a.access.key", os.environ["AWS_ACCESS_KEY_ID"])
            .config("spark.hadoop.fs.s3a.secret.key", os.environ["AWS_SECRET_ACCESS_KEY"])
            .config(
                "spark.hadoop.fs.s3a.aws.credentials.provider",
                "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
            )
        )
    return configure_spark_with_delta_pip(builder, extra_packages=extra_packages).getOrCreate()
