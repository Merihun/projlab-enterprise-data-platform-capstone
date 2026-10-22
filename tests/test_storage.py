from lakehouse.storage import bronze_path


def test_bronze_path():
    assert bronze_path("orders", bucket="demo") == "s3a://demo/bronze/orders"
