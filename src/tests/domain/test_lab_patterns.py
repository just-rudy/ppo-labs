from dataclasses import dataclass
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from application.services import CardLogic, DeckService, GameLogic, GameStateManager
from domain.entities import PendingAttack
from domain.enums import UserRole
from infrastructure.db.repositories.sqlalchemy_game_repository import (
    SqlAlchemyGameRepository,
)
from infrastructure.db.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)
from tests.builders import CardBuilder, ObjectMother, PlayerBuilder


@dataclass
class LondonContext:
    logic: GameLogic
    game_repository: Mock
    user_repository: Mock
    card_logic: Mock
    deck_service: Mock
    state_manager: Mock
    card_type_repository: Mock


@pytest.fixture()
def london_context() -> LondonContext:
    # Готовит SUT GameLogic и mock-объекты всех его сотрудников.
    game_repository = Mock()
    user_repository = Mock()
    card_logic = Mock(spec=CardLogic)
    deck_service = Mock(spec=DeckService)
    state_manager = Mock(spec=GameStateManager)
    card_type_repository = Mock()
    logic = GameLogic(
        game_repository,
        user_repository,
        card_logic,
        deck_service,
        state_manager,
        card_type_repository,
    )
    return LondonContext(
        logic,
        game_repository,
        user_repository,
        card_logic,
        deck_service,
        state_manager,
        card_type_repository,
    )


# Классическая школа: реальные объекты, проверка итогового состояния.


@pytest.mark.unit
@pytest.mark.classic
@pytest.mark.offline
def test_classic_draws_exactly_requested_cards() -> None:
    service = DeckService()
    cards = [CardBuilder().build() for _ in range(3)]
    player = PlayerBuilder().with_draw_pile(cards).build()

    drawn = service.draw(player.draw_deck, 2)

    assert drawn == cards[:2]
    assert player.draw_deck.cards == cards[2:]


@pytest.mark.unit
@pytest.mark.classic
@pytest.mark.offline
def test_classic_heal_is_capped_at_maximum_health() -> None:
    logic = CardLogic()
    healer = PlayerBuilder().build()
    target = PlayerBuilder().with_health(23).build()
    card = CardBuilder().with_power(5).with_echo(2).build()

    damage = logic.apply_effect(healer, card, ObjectMother.heal_card_type(), target)

    assert damage == 0
    assert target.health == 25
    assert healer.cur_echo == 2


@pytest.mark.unit
@pytest.mark.classic
@pytest.mark.offline
def test_classic_attack_without_target_is_rejected() -> None:
    logic = CardLogic()
    attacker = PlayerBuilder().build()
    card = CardBuilder().with_power(4).build()

    with pytest.raises(ValueError, match="ATTACK card requires a target player"):
        logic.apply_effect(attacker, card, ObjectMother.attack_card_type())


@pytest.mark.unit
@pytest.mark.classic
@pytest.mark.offline
def test_classic_next_turn_selects_player_by_turn_order() -> None:
    manager = GameStateManager()
    first = PlayerBuilder().with_turn_order(0).build()
    second = PlayerBuilder().with_turn_order(1).build()
    game = ObjectMother.game_with_players([first, second])

    manager.next_turn(game)

    assert game.cur_turn == 1
    assert game.cur_player_id == second.id


@pytest.mark.unit
@pytest.mark.classic
@pytest.mark.offline
def test_classic_end_turn_resolves_attack_recycles_cards_and_changes_turn(
    session: Session,
) -> None:
    hand_card = CardBuilder().with_title("Hand card").build()
    table_card = CardBuilder().with_title("Table card").build()
    draw_cards = [
        CardBuilder().with_title(f"Draw card {index}").build() for index in range(3)
    ]
    attacker = (
        PlayerBuilder()
        .with_turn_order(0)
        .with_base_echo(2)
        .with_current_echo(7)
        .with_hand_size(2)
        .with_hand([hand_card])
        .with_table([table_card])
        .with_draw_pile(draw_cards)
        .build()
    )
    defender = PlayerBuilder().with_turn_order(1).with_health(20).build()
    game = ObjectMother.game_with_players([attacker, defender])
    game.pending_attack = PendingAttack(attacker.id, defender.id, damage=4)
    repository = SqlAlchemyGameRepository(session)
    repository.save(game)
    logic = GameLogic(
        repository,
        SqlAlchemyUserRepository(session),
        CardLogic(),
        DeckService(),
        GameStateManager(),
    )

    logic.end_turn(game.id, attacker.id)

    saved_game = repository.get(game.id)
    saved_attacker = next(
        player for player in saved_game.players if player.id == attacker.id
    )
    saved_defender = next(
        player for player in saved_game.players if player.id == defender.id
    )

    assert saved_defender.health == 16
    assert saved_game.pending_attack is None
    assert saved_attacker.cur_echo == saved_attacker.base_echo == 2
    assert len(saved_attacker.hand_deck.cards) == 2
    assert hand_card.id in {card.id for card in saved_attacker.discard_deck.cards}
    assert table_card.id in {card.id for card in saved_attacker.discard_deck.cards}
    assert saved_game.cur_player_id == defender.id


# Лондонская школа: GameLogic — SUT, его сотрудники заменены mock-объектами.


@pytest.mark.unit
@pytest.mark.london
@pytest.mark.offline
def test_london_create_game_saves_created_entity(london_context: LondonContext) -> None:
    host_id = uuid4()

    game = london_context.logic.create_game(host_id, "Friday battle")

    assert game.host_user_id == host_id
    assert game.name == "Friday battle"
    london_context.game_repository.save.assert_called_once_with(game)


@pytest.mark.unit
@pytest.mark.london
@pytest.mark.offline
def test_london_add_player_promotes_user_and_saves_both_entities(
    london_context: LondonContext,
) -> None:
    game = ObjectMother.game_with_players([])
    user = ObjectMother.authenticated_user("alice")
    london_context.game_repository.get.return_value = game
    london_context.user_repository.get.return_value = user

    player = london_context.logic.add_player(game.id, user.id)

    assert player.nickname == "alice"
    assert user.role == UserRole.PLAYER
    london_context.user_repository.save.assert_called_once_with(user)
    london_context.game_repository.save.assert_called_once_with(game)


@pytest.mark.unit
@pytest.mark.london
@pytest.mark.offline
def test_london_buy_card_rejects_insufficient_echo(
    london_context: LondonContext,
) -> None:
    card = CardBuilder().with_cost(5).build()
    player = PlayerBuilder().with_current_echo(2).build()
    game = ObjectMother.game_with_players([player])
    game.market_deck.cards.append(card)
    london_context.game_repository.get.return_value = game
    london_context.state_manager.validate_turn.return_value = True
    london_context.card_logic.can_purchase.return_value = False

    with pytest.raises(ValueError, match="Card can't be purchased"):
        london_context.logic.buy_card(game.id, player.id, card.id)
    london_context.card_logic.can_purchase.assert_called_once_with(player, card)
    london_context.game_repository.save.assert_not_called()


@pytest.mark.unit
@pytest.mark.london
@pytest.mark.offline
def test_london_play_attack_delegates_effect_and_saves_pending_attack(
    london_context: LondonContext,
) -> None:
    attack_type = ObjectMother.attack_card_type()
    card = CardBuilder().with_card_type_id(attack_type.id).with_power(5).build()
    attacker = PlayerBuilder().with_hand([card]).build()
    defender = PlayerBuilder().build()
    game = ObjectMother.game_with_players([attacker, defender])
    london_context.game_repository.get.return_value = game
    london_context.state_manager.validate_turn.return_value = True
    london_context.card_logic.can_be_played.return_value = True
    london_context.card_logic.apply_effect.return_value = 5
    london_context.card_type_repository.get.return_value = attack_type

    london_context.logic.play_card(game.id, attacker.id, card.id, defender.id)

    london_context.card_logic.apply_effect.assert_called_once_with(
        attacker, card, attack_type, defender, london_context.deck_service
    )
    assert game.pending_attack == PendingAttack(attacker.id, defender.id, 5)
    london_context.game_repository.save.assert_called_once_with(game)


@pytest.mark.unit
@pytest.mark.london
@pytest.mark.offline
def test_london_defend_rejects_non_defense_card(london_context: LondonContext) -> None:
    card_type = ObjectMother.attack_card_type()
    card = CardBuilder().with_card_type_id(card_type.id).build()
    attacker = PlayerBuilder().build()
    defender = PlayerBuilder().with_hand([card]).build()
    game = ObjectMother.game_with_players([attacker, defender])
    game.pending_attack = PendingAttack(attacker.id, defender.id, damage=5)
    london_context.game_repository.get.return_value = game
    london_context.card_type_repository.get.return_value = card_type

    with pytest.raises(ValueError, match="Only DEF cards can be used to defend"):
        london_context.logic.defend(game.id, defender.id, card.id)
    london_context.card_logic.can_defend.assert_not_called()
    london_context.game_repository.save.assert_not_called()
