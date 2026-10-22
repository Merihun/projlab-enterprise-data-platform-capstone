"""Verify your lab. Run inside the workspace: python -m pytest -q tests/test_environment.py"""

import os
import shutil
import subprocess
import sys
import uuid

import pytest


def test_python_version():
    assert sys.version_info[:2] == (3, 12), sys.version


def test_packages_import():
    import boto3  # noqa: F401
    import confluent_kafka  # noqa: F401
    import psycopg  # noqa: F401
    import delta  # noqa: F401
    import jupyterlab  # noqa: F401
    import pyspark

    assert pyspark.__version__.startswith("3.5."), pyspark.__version__


def test_java_17_is_available():
    java = shutil.which("java")
    assert java, "java not found; rebuild the container"
    out = subprocess.run([java, "-version"], capture_output=True, text=True).stderr
    assert '"17.' in out, out


@pytest.fixture(scope="module")
def spark():
    from lakehouse.spark import get_spark

    session = get_spark("projlab-verify")
    yield session
    session.stop()


@pytest.mark.spark
def test_delta_table_roundtrip(spark, tmp_path):
    path = str(tmp_path / "orders")
    spark.createDataFrame([(1, "placed"), (2, "shipped")], "id INT, status STRING").write.format("delta").save(path)
    spark.sql(f"UPDATE delta.`{path}` SET status = 'shipped' WHERE id = 1")
    rows = spark.read.format("delta").load(path).orderBy("id").collect()
    assert [(r.id, r.status) for r in rows] == [(1, "shipped"), (2, "shipped")]
    history = spark.sql(f"DESCRIBE HISTORY delta.`{path}`").count()
    assert history == 2


@pytest.mark.service
def test_object_storage_roundtrip():
    from lakehouse.storage import s3_client

    s3 = s3_client()
    bucket = os.environ.get("S3_BUCKET", "lakehouse")
    buckets = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    assert bucket in buckets, f"bucket {bucket!r} missing; reset with: docker compose down -v"
    key = f"_verify/{uuid.uuid4()}.txt"
    s3.put_object(Bucket=bucket, Key=key, Body=b"hello lakehouse")
    assert s3.get_object(Bucket=bucket, Key=key)["Body"].read() == b"hello lakehouse"
    s3.delete_object(Bucket=bucket, Key=key)


@pytest.mark.service
@pytest.mark.spark
@pytest.mark.skipif(
    os.environ.get("PROJLAB_TEST_S3A") != "1",
    reason="opt-in: downloads ~300 MB of hadoop-aws jars; run with PROJLAB_TEST_S3A=1",
)
def test_delta_table_on_object_storage():
    # Spark's JVM (and its packages) is fixed per Python process, and other tests already started one
    # without hadoop-aws, so this check runs in a fresh interpreter.
    path = f"s3a://{os.environ.get('S3_BUCKET', 'lakehouse')}/_verify/{uuid.uuid4()}"
    script = (
        "import sys\n"
        "from lakehouse.spark import get_spark\n"
        "spark = get_spark('projlab-verify-s3', s3=True)\n"
        "spark.range(5).write.format('delta').save(sys.argv[1])\n"
        "assert spark.read.format('delta').load(sys.argv[1]).count() == 5\n"
        "spark.stop()\n"
    )
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [src, os.environ.get("PYTHONPATH")]))}
    result = subprocess.run(
        [sys.executable, "-c", script, path], capture_output=True, text=True, timeout=900, env=env
    )
    assert result.returncode == 0, result.stderr[-3000:]


@pytest.mark.service
def test_kafka_roundtrip():
    from confluent_kafka import Consumer, Producer

    servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    topic, key = "_verify", str(uuid.uuid4())
    producer = Producer({"bootstrap.servers": servers})
    producer.produce(topic, key=key, value=b"hello kafka")
    assert producer.flush(30) == 0, f"could not deliver to Kafka at {servers}"
    consumer = Consumer({"bootstrap.servers": servers, "group.id": key, "auto.offset.reset": "earliest"})
    consumer.subscribe([topic])
    try:
        for _ in range(60):
            message = consumer.poll(1.0)
            if message is not None and not message.error() and message.key() == key.encode():
                assert message.value() == b"hello kafka"
                return
        pytest.fail("the message never came back from Kafka")
    finally:
        consumer.close()


@pytest.mark.service
def test_postgres_has_pgvector():
    import psycopg

    with psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        user=os.environ.get("POSTGRES_USER", "projlab"),
        password=os.environ.get("POSTGRES_PASSWORD", "projlab"),
        dbname=os.environ.get("POSTGRES_DB", "projlab"),
        connect_timeout=5,
    ) as conn:
        version = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
        assert version, "pgvector is not enabled; reset the database with: docker compose down -v"
        distance = conn.execute("SELECT '[1,0,0]'::vector <-> '[0,1,0]'::vector").fetchone()[0]
    assert round(distance, 4) == 1.4142
