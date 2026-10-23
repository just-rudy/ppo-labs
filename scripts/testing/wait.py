import argparse
import time

import httpx
from scripts.testing.storage import object_storage, test_engine
from sqlalchemy import text


def wait(kind, timeout=90):
    deadline = time.monotonic() + timeout
    error = None
    while time.monotonic() < deadline:
        try:
            if kind == "storage":
                engine = test_engine()
                try:
                    with engine.connect() as connection:
                        connection.execute(text("SELECT 1"))
                finally:
                    engine.dispose()
                client, _ = object_storage()
                client.list_buckets()
            else:
                with httpx.Client(timeout=3) as client:
                    response = client.get("http://api:8000/openapi.json")
                    response.raise_for_status()
            print(f"{kind} ready", flush=True)
            return
        except Exception as exc:
            error = exc
            time.sleep(1)
    raise RuntimeError(f"{kind} not ready after {timeout}s: {error}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["storage", "api"])
    wait(parser.parse_args().kind)
