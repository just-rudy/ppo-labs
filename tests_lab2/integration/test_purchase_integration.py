from uuid import uuid4

import allure
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from application.dto.requests import CreateGameRequest
from domain.entities import User
from infrastructure.db.repositories.sqlalchemy_game_repository import (
    SqlAlchemyGameRepository,
)
from infrastructure.db.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)

pytestmark = pytest.mark.integration


def test_purchase_function_and_business_service(engine, db_session, service):
    user = User(id=uuid4(), username="buyer")
    SqlAlchemyUserRepository(db_session).save(user)
    game = service.create_new_game(
        CreateGameRequest(host_user_id=user.id, name="purchase-room")
    )
    service.join_game(game.id, user.id)
    game = service.start_game(game.id)
    player = game.players[0]
    card = game.market_deck.cards[0]
    with allure.step(
        "Insufficient echo rejected by business logic and SQL independently"
    ):
        with pytest.raises(ValueError, match="can't be purchased"):
            service.buy_card(game.id, player.id, card.id)
        with engine.connect() as connection:
            with pytest.raises(DBAPIError, match="Insufficient echo"):
                connection.execute(
                    text("SELECT purchase_card(:p, :c)"), {"p": player.id, "c": card.id}
                )
            connection.rollback()
        with Session(engine) as fresh:
            saved = SqlAlchemyGameRepository(fresh).get(game.id)
            assert saved.players[0].cur_echo == 0
            assert card.id in {c.id for c in saved.market_deck.cards}
    with allure.step(
        "Play card to earn echo, buy with real SQL function, check fresh state"
    ):
        service.play_card(game.id, player.id, player.hand_deck.cards[0].id)
        game = service.buy_card(game.id, player.id, card.id)
        with Session(engine) as fresh:
            saved = SqlAlchemyGameRepository(fresh).get(game.id)
            buyer = saved.players[0]
            assert buyer.cur_echo == 0
            assert card.id not in {c.id for c in saved.market_deck.cards}
            assert [c.id for c in buyer.discard_deck.cards] == [card.id]
