import os

import pytest
from scripts.testing.storage import reset, test_engine
from sqlalchemy.orm import Session

from application.services.card_logic import CardLogic
from application.services.deck_service import DeckService
from application.services.game_service import GameAppService
from application.services.game_state_manager import GameStateManager
from infrastructure.db.repositories.sqlalchemy_card_repository import (
    SqlAlchemyCardRepository,
)
from infrastructure.db.repositories.sqlalchemy_card_type_repository import (
    SqlAlchemyCardTypeRepository,
)
from infrastructure.db.repositories.sqlalchemy_game_repository import (
    SqlAlchemyGameRepository,
)
from infrastructure.db.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)


@pytest.fixture
def engine():
    reset()
    db = test_engine()
    try:
        yield db
    finally:
        db.dispose()


@pytest.fixture
def db_session(engine):
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def service(db_session):
    return GameAppService(
        SqlAlchemyGameRepository(db_session),
        SqlAlchemyUserRepository(db_session),
        CardLogic(),
        DeckService(),
        GameStateManager(),
        SqlAlchemyCardRepository(db_session),
        card_type_repository=SqlAlchemyCardTypeRepository(db_session),
        db_session=db_session,
    )


@pytest.fixture
def api_url():
    return os.environ["API_BASE_URL"]
