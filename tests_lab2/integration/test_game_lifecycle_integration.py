from uuid import uuid4

import allure
import pytest
from sqlalchemy.orm import Session

from application.dto.requests import CreateGameRequest
from domain.entities import User
from domain.enums import GameStatus, UserRole
from infrastructure.db.repositories.sqlalchemy_game_repository import (
    SqlAlchemyGameRepository,
)
from infrastructure.db.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)

pytestmark = pytest.mark.integration


def test_service_game_lifecycle_with_postgres(engine, db_session, service):
    users = [User(id=uuid4(), username=name) for name in ("host", "guest")]
    for user in users:
        SqlAlchemyUserRepository(db_session).save(user)
    with allure.step("Create a game and join two users through the business service"):
        game = service.create_new_game(
            CreateGameRequest(host_user_id=users[0].id, name="integration-room")
        )
        assert game.status == GameStatus.CREATED
        for user in users:
            service.join_game(game.id, user.id)
        with Session(engine) as fresh:
            saved = SqlAlchemyGameRepository(fresh).get(game.id)
            assert {p.user_id for p in saved.players} == {u.id for u in users}
            assert all(
                SqlAlchemyUserRepository(fresh).get(u.id).role == UserRole.PLAYER
                for u in users
            )
    with allure.step(
        "Duplicate join fails and leaves the persisted participants unchanged"
    ):
        with pytest.raises(ValueError, match="already in"):
            service.join_game(game.id, users[0].id)
        with Session(engine) as fresh:
            assert len(SqlAlchemyGameRepository(fresh).get(game.id).players) == 2
    with allure.step("Start game; decks and current player survive a new connection"):
        game = service.start_game(game.id)
        with Session(engine) as fresh:
            saved = SqlAlchemyGameRepository(fresh).get(game.id)
            assert saved.status == GameStatus.IN_PROGRESS
            assert saved.cur_player_id in {p.id for p in saved.players}
            assert len(saved.market_deck.cards) == 5
            assert all(len(p.hand_deck.cards) == 5 for p in saved.players)
    with allure.step("End turn and finish; verify committed winner and status"):
        previous = game.cur_player_id
        game = service.end_turn(game.id, previous)
        assert game.cur_player_id != previous
        service.finish_game(game.id, game.players[0].id)
        with Session(engine) as fresh:
            saved = SqlAlchemyGameRepository(fresh).get(game.id)
            assert saved.status == GameStatus.FINISHED
            assert saved.cur_player_id is None
            assert saved.winner_id in {p.id for p in saved.players}
