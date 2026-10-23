from uuid import uuid4

import allure
import pytest
from scripts.testing.storage import stable_id
from sqlalchemy.orm import Session

from infrastructure.db.exceptions import EntityNotFoundError, PersistenceError
from infrastructure.db.repositories.sqlalchemy_card_repository import (
    SqlAlchemyCardRepository,
)

pytestmark = pytest.mark.integration


def test_card_repository_roundtrip_update_reject_and_delete(engine, db_session):
    repository = SqlAlchemyCardRepository(db_session)
    card = repository.get(stable_id("card-0"))
    card.id = uuid4()
    card.title = "Repository integration card"
    with allure.step("Save card with real foreign keys; verify in fresh Session"):
        repository.save(card)
        with Session(engine) as fresh:
            loaded = SqlAlchemyCardRepository(fresh).get(card.id)
            assert loaded.title == card.title
            assert loaded.image.id == stable_id("image")
            assert loaded.card_type.action.value == "heal"
    with allure.step("Update cost; PostgreSQL rejects subsequent invalid update"):
        card.cost = 7
        repository.save(card)
        card.cost = 8
        with pytest.raises(PersistenceError):
            repository.save(card)
        with Session(engine) as fresh:
            assert SqlAlchemyCardRepository(fresh).get(card.id).cost == 7
    with allure.step("Delete and verify missing-card exception via fresh Session"):
        repository.delete(card.id)
        with Session(engine) as fresh:
            with pytest.raises(EntityNotFoundError):
                SqlAlchemyCardRepository(fresh).get(card.id)
