import allure
import pytest
from scripts.testing.storage import stable_id
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration


def test_postgres_card_trigger_boundaries(engine):
    card = stable_id("card-0")
    with allure.step("Database accepts inclusive cost boundaries"):
        for cost in (1, 7):
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE cards SET cost=:cost WHERE id=:id"),
                    {"cost": cost, "id": card},
                )
            with engine.connect() as fresh:
                assert (
                    fresh.scalar(
                        text("SELECT cost FROM cards WHERE id=:id"), {"id": card}
                    )
                    == cost
                )
    with allure.step(
        "Invalid costs, power and points fail in PostgreSQL; committed row unchanged"
    ):
        for field, value, message in (
            ("cost", 0, "Card cost"),
            ("cost", 8, "Card cost"),
            ("power", 0, "Card power"),
            ("cool_points", -2, "cool_points"),
            ("cool_points", 6, "cool_points"),
        ):
            with engine.connect() as connection:
                before = dict(
                    connection.execute(
                        text("SELECT * FROM cards WHERE id=:id"), {"id": card}
                    )
                    .mappings()
                    .one()
                )
                with pytest.raises(DBAPIError, match=message):
                    connection.execute(
                        text(f"UPDATE cards SET {field}=:value WHERE id=:id"),
                        {"value": value, "id": card},
                    )
                connection.rollback()
            with engine.connect() as fresh:
                assert (
                    dict(
                        fresh.execute(
                            text("SELECT * FROM cards WHERE id=:id"), {"id": card}
                        )
                        .mappings()
                        .one()
                    )
                    == before
                )
