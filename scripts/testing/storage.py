"""Deterministic seed, guarded reset and full baseline verification."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from alembic import command
from alembic.config import Config
from minio import Minio
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from urllib3 import PoolManager, Timeout

from infrastructure.db.models import CardModel, CardTypeModel, ImageModel


def stable_id(name):
    return uuid5(NAMESPACE_URL, f"cmb-lab2/{name}")


def test_engine():
    url = os.environ.get("DATABASE_URL", "")
    parsed = make_url(url)
    if (
        os.environ.get("CMB_TESTING") != "1"
        or parsed.database != "cmb_test"
        or parsed.get_backend_name() != "postgresql"
    ):
        raise RuntimeError(
            "Refusing destructive operation outside CMB_TESTING=1 / cmb_test"
        )
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=30000"},
    )
    with engine.connect() as connection:
        if connection.scalar(text("SELECT current_database()")) != "cmb_test":
            raise RuntimeError("Unexpected database")
    return engine


def object_storage():
    bucket = os.environ.get("MINIO_BUCKET")
    if os.environ.get("CMB_TESTING") != "1" or bucket != "cards-test":
        raise RuntimeError("Refusing to reset non-test object storage")
    client = Minio(
        os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False,
        http_client=PoolManager(timeout=Timeout(connect=3, read=5), retries=False),
    )
    return client, bucket


def reset():
    engine = test_engine()
    try:
        # Only this Compose project's instance; no production URL fallback.
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        command.upgrade(Config("alembic.ini"), "head")
        # Remove migration seed rows: the baseline is entirely deterministic.
        names = inspect(engine).get_table_names(schema="public")
        names = [name for name in names if name != "alembic_version"]
        quoted = ", ".join(engine.dialect.identifier_preparer.quote(n) for n in names)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
        with Session(engine) as session:
            session.add(
                CardTypeModel(
                    id=stable_id("heal"),
                    action="heal",
                    usage_pattern="reg",
                    if_permanent=False,
                    color="green",
                )
            )
            session.add(ImageModel(id=stable_id("image"), title="Lab image", file=None))
            session.commit()
            session.add_all(
                [
                    CardModel(
                        id=stable_id(f"card-{i}"),
                        title=f"Lab heal {i:02}",
                        creature="wizard",
                        card_type_id=stable_id("heal"),
                        image_id=stable_id("image"),
                        power=1,
                        echo=1,
                        cost=1,
                        cool_points=0,
                    )
                    for i in range(50)
                ]
            )
            session.commit()
        client, bucket = object_storage()
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        for obj in client.list_objects(bucket, recursive=True):
            client.remove_object(bucket, obj.object_name)
    finally:
        engine.dispose()


def snapshot():
    engine = test_engine()
    try:
        data = {}
        with engine.connect() as connection:
            for name in sorted(inspect(engine).get_table_names(schema="public")):
                quoted = engine.dialect.identifier_preparer.quote(name)
                rows = [
                    dict(row)
                    for row in connection.execute(
                        text(f"SELECT * FROM {quoted}")
                    ).mappings()
                ]
                data[name] = sorted(
                    [json.loads(json.dumps(row, default=str)) for row in rows],
                    key=lambda row: json.dumps(row, sort_keys=True),
                )
            data["functions"] = connection.execute(text("""
                SELECT p.proname, pg_get_functiondef(p.oid) FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace=n.oid
                WHERE n.nspname='public' AND p.prokind='f' ORDER BY p.proname
            """)).all()
            data["triggers"] = connection.execute(text("""
                SELECT pg_get_triggerdef(t.oid) FROM pg_trigger t
                JOIN pg_class c ON c.oid=t.tgrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY t.tgname
            """)).all()
        data["functions"] = [list(row) for row in data["functions"]]
        data["triggers"] = [list(row) for row in data["triggers"]]
        client, bucket = object_storage()
        data["objects"] = sorted(
            obj.object_name for obj in client.list_objects(bucket, recursive=True)
        )
        return data
    finally:
        engine.dispose()


def verify(expected_path):
    actual = snapshot()
    expected = json.loads(Path(expected_path).read_text())
    if actual != expected:
        Path("/artifacts/baseline-mismatch.json").write_text(
            json.dumps(actual, indent=2, default=str)
        )
        raise AssertionError(
            "Full database/object-storage baseline differs; see baseline-mismatch.json"
        )
    assert len(actual["cards"]) == 50
    assert not actual["users"] and not actual["games"] and not actual["players"]
    assert {row[0] for row in actual["functions"]} >= {
        "purchase_card",
        "card_validate_trigger",
    }
    assert actual["triggers"]
    digest = hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest()
    print(f"BASELINE VERIFIED sha256={digest}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["reset", "snapshot", "verify"])
    parser.add_argument("--file", default="/artifacts/baseline.json")
    args = parser.parse_args()
    if args.action == "reset":
        reset()
    elif args.action == "snapshot":
        Path(args.file).write_text(json.dumps(snapshot(), indent=2, default=str))
    else:
        verify(args.file)


if __name__ == "__main__":
    main()
