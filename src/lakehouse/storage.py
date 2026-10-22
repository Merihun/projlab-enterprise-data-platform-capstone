"""Object storage helpers (S3 API) for the lab's SeaweedFS service."""

from __future__ import annotations

import os

import boto3


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT_URL", "http://localhost:8333"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "projlab"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "projlab-local-secret"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )


def bronze_path(table: str, bucket: str | None = None) -> str:
    """Where a bronze table lives in object storage, e.g. s3a://lakehouse/bronze/orders."""
    return f"s3a://{bucket or os.environ.get('S3_BUCKET', 'lakehouse')}/bronze/{table}"
