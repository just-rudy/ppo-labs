from collections.abc import Callable
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pytest import MonkeyPatch

from application.services import CardLogic, DeckService, GameLogic, GameStateManager
from domain.entities import Card, Deck, Game, Player, User
from domain.enums import GameStatus


@pytest.fixture
def game_logic() -> tuple[GameLogic, Mock, Mock, Mock, Mock, Mock]:
    game_repository = Mock()
    user_repository = Mock()
    card_logic = Mock(spec=CardLogic)
    deck_service = Mock(spec=DeckService)
    state_manager = Mock(spec=GameStateManager)

    logic = GameLogic(
        game_repository=game_repository,
        user_repository=user_repository,
        card_logic=card_logic,
        deck_service=deck_service,
        game_state_manager=state_manager,
        card_type_repository=None,
    )

    return (
        logic,
        game_repository,
        user_repository,
        card_logic,
        deck_service,
        state_manager,
    )


def test_get_player_returns_player_from_game(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
) -> None:
    logic, *_ = game_logic
    player = make_player()
    other_player = make_player()
    game = make_game(host_user_id=uuid4(), players=[player, other_player])

    result = logic._get_player(game, player.id)

    assert result == player


def test_get_player_raises_error_when_player_not_found_game_empty(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
) -> None:
    logic, *_ = game_logic
    game = make_game(host_user_id=uuid4(), players=[])

    with pytest.raises(ValueError, match="Player not found in game"):
        logic._get_player(game, uuid4())


def test_get_player_raises_error_when_player_not_found(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
) -> None:
    logic, *_ = game_logic
    player = make_player()
    other_player = make_player()
    game = make_game(host_user_id=uuid4(), players=[other_player])

    with pytest.raises(ValueError, match="Player not found in game"):
        logic._get_player(game, player_id=player.id)


def test_get_card_returns_card_from_deck(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_deck: Callable[..., Deck],
    make_card: Callable[..., Card],
) -> None:
    logic, *_ = game_logic
    card = make_card()
    deck = make_deck(cards=[card])

    result = logic._get_card(deck, card.id)

    assert result == card


def test_get_card_raises_error_when_card_not_found_empty_deck(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_deck: Callable[..., Deck],
) -> None:
    logic, *_ = game_logic
    deck = make_deck(cards=[])

    with pytest.raises(ValueError, match="Card not in deck"):
        logic._get_card(deck, uuid4())


def test_get_card_raises_error_when_card_not_found(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_deck: Callable[..., Deck],
    make_card: Callable[..., Card],
) -> None:
    logic, *_ = game_logic
    card = make_card()
    other_card = make_card()
    deck = make_deck(cards=[other_card])

    with pytest.raises(ValueError, match="Card not in deck"):
        logic._get_card(deck, card.id)


def test_create_game_creates_and_saves_game(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
) -> None:
    logic, game_repository, *_ = game_logic
    host_user_id = uuid4()

    game = logic.create_game(host_user_id)

    assert game.host_user_id == host_user_id
    game_repository.save.assert_called_once_with(game)


def test_order_player_turns_sets_turn_order_in_shuffled_order(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    monkeypatch: MonkeyPatch,
) -> None:
    logic, *_ = game_logic
    p1 = make_player(nickname="zeta")
    p2 = make_player(nickname="alpha")
    p3 = make_player(nickname="gamma")
    game = make_game(host_user_id=uuid4(), players=[p1, p2, p3])

    def fake_shuffle(players: list[Player]) -> None:
        players[:] = [p2, p3, p1]

    monkeypatch.setattr("application.services.game_logic.random.shuffle", fake_shuffle)

    result = logic.order_player_turns(game)

    assert result.players == [p2, p3, p1]
    assert result.players[0].turn_order == 0
    assert result.players[1].turn_order == 1
    assert result.players[2].turn_order == 2


def test_start_game_sets_in_progress_orders_players_and_saves(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    monkeypatch: MonkeyPatch,
) -> None:
    logic, game_repository, *_ = game_logic

    p1 = make_player(nickname="b")
    p2 = make_player(nickname="a")
    game = make_game(host_user_id=uuid4(), players=[p1, p2], status=GameStatus.CREATED)
    game_repository.get.return_value = game

    called = {"value": False}

    def fake_order_player_turns(arg_game: Game) -> Game:
        called["value"] = True
        assert arg_game is game

        arg_game.players[:] = [p2, p1]
        arg_game.players[0].turn_order = 0
        arg_game.players[1].turn_order = 1
        return arg_game

    monkeypatch.setattr(logic, "order_player_turns", fake_order_player_turns)

    logic.start_game(game.id)

    assert game.status == GameStatus.IN_PROGRESS
    assert called["value"] is True
    assert game.players == [p2, p1]
    assert [p.turn_order for p in game.players] == [0, 1]
    game_repository.save.assert_called_once_with(game)


def test_start_game_raises_error_if_already_in_progress(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
) -> None:
    logic, game_repository, *_ = game_logic
    game = make_game(host_user_id=uuid4(), status=GameStatus.IN_PROGRESS)
    game_repository.get.return_value = game

    with pytest.raises(ValueError, match="Game already in progress"):
        logic.start_game(game.id)


def test_finish_game_marks_game_finished_and_clears_current_player(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
    make_deck: Callable[..., Deck],
) -> None:
    logic, game_repository, *_ = game_logic
    stronger = make_player(
        nickname="stronger",
        draw_deck=make_deck(cards=[make_card(cool_points=3), make_card(cool_points=2)]),
    )
    weaker = make_player(
        nickname="weaker",
        draw_deck=make_deck(cards=[make_card(cool_points=1)]),
    )
    game = make_game(
        host_user_id=uuid4(),
        players=[stronger, weaker],
        status=GameStatus.IN_PROGRESS,
        cur_player_id=stronger.id,
    )
    game_repository.get.return_value = game

    logic.finish_game(game.id, stronger.id)

    assert game.status == GameStatus.FINISHED
    assert game.cur_player_id is None
    assert game.winner_id == stronger.id
    game_repository.save.assert_called_once_with(game)


def test_finish_game_raises_error_when_game_already_finished(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
) -> None:
    logic, game_repository, *_ = game_logic
    player = make_player()
    game = make_game(
        host_user_id=uuid4(),
        players=[player],
        status=GameStatus.FINISHED,
    )
    game_repository.get.return_value = game

    with pytest.raises(ValueError, match="Game already finished"):
        logic.finish_game(game.id, player.id)


def test_finish_game_uses_cards_count_as_tie_breaker(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
    make_deck: Callable[..., Deck],
) -> None:
    logic, game_repository, *_ = game_logic
    first = make_player(
        nickname="first",
        draw_deck=make_deck(cards=[make_card(cool_points=2), make_card(cool_points=1)]),
    )
    second = make_player(
        nickname="second",
        draw_deck=make_deck(cards=[make_card(cool_points=3)]),
    )
    game = make_game(
        host_user_id=uuid4(),
        players=[first, second],
        status=GameStatus.IN_PROGRESS,
        cur_player_id=first.id,
    )
    game_repository.get.return_value = game

    logic.finish_game(game.id, first.id)

    assert game.winner_id == first.id


def test_add_player_creates_player_and_saves_game(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_user: Callable[..., User],
) -> None:
    logic, game_repository, user_repository, *_ = game_logic
    user_id = uuid4()
    user = make_user(username="new_user")
    user.id = user_id
    game = make_game(host_user_id=uuid4(), players=[])

    game_repository.get.return_value = game
    user_repository.get.return_value = user

    player = logic.add_player(game.id, user_id)

    assert player.user_id == user_id
    assert player.nickname == "new_user"
    assert player in game.players
    game_repository.save.assert_called_once_with(game)


def test_add_player_raises_error_if_user_already_in_game(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
) -> None:
    logic, game_repository, *_ = game_logic
    user_id = uuid4()
    existing_player = make_player(user_id=user_id)
    game = make_game(host_user_id=uuid4(), players=[existing_player])
    game_repository.get.return_value = game

    with pytest.raises(ValueError, match="User is already in the game"):
        logic.add_player(game.id, user_id)


def test_buy_card_raises_error_when_game_not_in_progress(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
    make_deck: Callable[..., Deck],
) -> None:
    logic, game_repository, *_ = game_logic
    player = make_player()
    card = make_card()
    market_deck = make_deck(cards=[card])
    game = make_game(
        host_user_id=uuid4(),
        players=[player],
        status=GameStatus.CREATED,
        cur_player_id=player.id,
        market_deck=market_deck,
    )
    game_repository.get.return_value = game

    with pytest.raises(ValueError, match="Game not in progress"):
        logic.buy_card(game.id, player.id, card.id)


def test_buy_card_raises_error_when_not_players_turn(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
    make_deck: Callable[..., Deck],
) -> None:
    logic, game_repository, _, _, _, state_manager = game_logic
    player = make_player()
    card = make_card()
    market_deck = make_deck(cards=[card])
    game = make_game(
        host_user_id=uuid4(),
        players=[player],
        status=GameStatus.IN_PROGRESS,
        market_deck=market_deck,
    )
    game_repository.get.return_value = game
    state_manager.validate_turn.side_effect = ValueError("Not your turn")

    with pytest.raises(ValueError, match="Not your turn"):
        logic.buy_card(game.id, player.id, card.id)


def test_buy_card_raises_error_when_card_cant_be_bought(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
    make_deck: Callable[..., Deck],
) -> None:
    logic, game_repository, _, card_logic, _, state_manager = game_logic
    player = make_player()
    card = make_card(cost=3)
    market_deck = make_deck(cards=[card])
    game = make_game(
        host_user_id=uuid4(),
        players=[player],
        status=GameStatus.IN_PROGRESS,
        cur_player_id=player.id,
        market_deck=market_deck,
    )
    game_repository.get.return_value = game
    state_manager.validate_turn.return_value = True
    card_logic.can_purchase.return_value = False

    with pytest.raises(ValueError, match="Card can't be purchased"):
        logic.buy_card(game.id, player.id, card.id)


def test_buy_card_moves_card_from_market_to_discard_and_decreases_echo(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
    make_deck: Callable[..., Deck],
) -> None:
    logic, game_repository, _, card_logic, _, state_manager = game_logic
    player = make_player(cur_echo=5)
    card = make_card(cost=3)
    market_deck = make_deck(cards=[card])
    game = make_game(
        host_user_id=uuid4(),
        players=[player],
        status=GameStatus.IN_PROGRESS,
        cur_player_id=player.id,
        market_deck=market_deck,
    )
    game_repository.get.return_value = game
    state_manager.validate_turn.return_value = True
    card_logic.can_be_played.return_value = True

    logic.buy_card(game.id, player.id, card.id)

    assert player.cur_echo == 2
    assert card in player.discard_deck.cards
    assert card not in game.market_deck.cards
    game_repository.save.assert_called_once_with(game)


def test_play_card_raises_error_when_game_not_in_progress(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
    make_deck: Callable[..., Deck],
) -> None:
    logic, game_repository, *_ = game_logic
    player = make_player()
    card = make_card()
    market_deck = make_deck(cards=[card])
    game = make_game(
        host_user_id=uuid4(),
        players=[player],
        status=GameStatus.CREATED,
        cur_player_id=player.id,
        market_deck=market_deck,
    )
    game_repository.get.return_value = game

    with pytest.raises(ValueError, match="Game not in progress"):
        logic.play_card(game.id, player.id, card.id)


def test_play_card_raises_error_when_not_players_turn(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
    make_deck: Callable[..., Deck],
) -> None:
    logic, game_repository, _, _, _, state_manager = game_logic
    player = make_player()
    card = make_card()
    market_deck = make_deck(cards=[card])
    game = make_game(
        host_user_id=uuid4(),
        players=[player],
        status=GameStatus.IN_PROGRESS,
        market_deck=market_deck,
    )
    game_repository.get.return_value = game
    state_manager.validate_turn.side_effect = ValueError("Not your turn")

    with pytest.raises(ValueError, match="Not your turn"):
        logic.play_card(game.id, player.id, card.id)


def test_play_card_raises_error_when_card_cant_be_played(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
    make_deck: Callable[..., Deck],
) -> None:
    logic, game_repository, _, card_logic, _, state_manager = game_logic
    card = make_card()
    hand_deck = make_deck(cards=[card])
    player = make_player(hand_deck=hand_deck)
    game = make_game(
        host_user_id=uuid4(),
        players=[player],
        status=GameStatus.IN_PROGRESS,
        cur_player_id=player.id,
    )

    game_repository.get.return_value = game
    state_manager.validate_turn.return_value = True
    card_logic.can_be_played.return_value = False

    with pytest.raises(ValueError, match="Card can't be played"):
        logic.play_card(game.id, player.id, card.id)


def test_play_card_moves_card_from_hand_to_table_cur_expected_domain_behavior(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
    make_deck: Callable[..., Deck],
) -> None:
    logic, game_repository, _, card_logic, _, state_manager = game_logic
    player = make_player()
    card = make_card()
    player.hand_deck.cards.append(card)

    game = make_game(
        host_user_id=uuid4(),
        players=[player],
        status=GameStatus.IN_PROGRESS,
        cur_player_id=player.id,
    )
    game_repository.get.return_value = game
    state_manager.validate_turn.return_value = True
    card_logic.can_be_played.return_value = True
    card_logic.apply_effect.return_value = 0  # Возвращаем 0 (нет урона)

    logic.play_card(game.id, player.id, card.id)

    assert card not in player.hand_deck.cards
    assert card in player.table_deck.cards
    card_logic.apply_effect.assert_called_once_with(
        player, card, None, None, logic._deck_service
    )
    game_repository.save.assert_called_once_with(game)


def test_end_turn_raises_error_when_not_players_turn(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
) -> None:
    logic, game_repository, _, _, _, state_manager = game_logic
    player = make_player()
    game = make_game(host_user_id=uuid4(), players=[player])
    game_repository.get.return_value = game
    state_manager.validate_turn.side_effect = ValueError("Not your turn")

    with pytest.raises(ValueError, match="Not your turn"):
        logic.end_turn(game.id, player.id)


def test_end_turn_discards_cards_draws_new_hand_calls_next_turn_and_saves(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
) -> None:
    logic, game_repository, _, _, deck_service, state_manager = game_logic

    hand_cards = [make_card(title="h1"), make_card(title="h2")]
    table_cards = [make_card(title="t1")]
    draw_cards = [make_card(title="d1"), make_card(title="d2"), make_card(title="d3")]

    player = make_player(cur_echo=5, hand_size=3)
    player.hand_deck.cards = hand_cards.copy()
    player.table_deck.cards = table_cards.copy()
    player.draw_deck.cards = draw_cards.copy()
    player.discard_deck.cards = []

    game = make_game(host_user_id=uuid4(), players=[player], cur_player_id=player.id)
    game_repository.get.return_value = game
    state_manager.validate_turn.return_value = True
    deck_service.draw.return_value = draw_cards.copy()

    logic.end_turn(game.id, player.id)

    assert player.cur_echo == 0
    assert player.hand_deck.cards == draw_cards
    assert player.table_deck.cards == []
    assert player.discard_deck.cards == hand_cards + table_cards

    deck_service.draw.assert_called_once_with(player.draw_deck, player.hand_size)
    state_manager.next_turn.assert_called_once_with(game)
    game_repository.save.assert_called_once_with(game)


def test_end_turn_shuffles_discard_into_draw_deck_when_cards_are_insufficient(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
) -> None:
    logic, game_repository, _, _, deck_service, state_manager = game_logic

    draw_cards = [make_card(title="d1")]
    discard_existing = [make_card(title="old_discard")]
    hand_cards = [make_card(title="h1")]
    table_cards = [make_card(title="t1")]
    new_hand = [make_card(title="n1"), make_card(title="n2")]

    player = make_player(cur_echo=2, hand_size=2)
    player.draw_deck.cards = draw_cards.copy()
    player.discard_deck.cards = discard_existing.copy()
    player.hand_deck.cards = hand_cards.copy()
    player.table_deck.cards = table_cards.copy()

    game = make_game(host_user_id=uuid4(), players=[player], cur_player_id=player.id)
    game_repository.get.return_value = game
    state_manager.validate_turn.return_value = True
    deck_service.draw.return_value = new_hand.copy()

    logic.end_turn(game.id, player.id)

    assert player.cur_echo == 0
    assert (
        player.draw_deck.cards
        == draw_cards + discard_existing + hand_cards + table_cards
    )
    assert player.discard_deck.cards == []
    assert player.table_deck.cards == []
    assert player.hand_deck.cards == new_hand

    deck_service.shuffle.assert_called_once_with(player.draw_deck)
    deck_service.draw.assert_called_once_with(player.draw_deck, player.hand_size)
    state_manager.next_turn.assert_called_once_with(game)
    game_repository.save.assert_called_once_with(game)


def test_play_card_attack_creates_pending_attack(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
) -> None:
    from domain.entities.card_type import CardType
    from domain.enums import CardAction, UsePattern

    logic, game_repository, _, card_logic, _, state_manager = game_logic
    attacker = make_player(nickname="attacker")
    defender = make_player(nickname="defender")
    card = make_card(power=5)
    attacker.hand_deck.cards.append(card)

    card_type = CardType(
        id=uuid4(), action=CardAction.ATTACK, usage_pattern=UsePattern.REG
    )

    game = make_game(
        host_user_id=uuid4(),
        players=[attacker, defender],
        status=GameStatus.IN_PROGRESS,
        cur_player_id=attacker.id,
    )
    game_repository.get.return_value = game
    state_manager.validate_turn.return_value = True
    card_logic.can_be_played.return_value = True
    card_logic.apply_effect.return_value = 5  # Возвращаем урон
    
    # Мокаем card_type_repository
    logic._card_type_repo = Mock()
    logic._card_type_repo.get.return_value = card_type

    logic.play_card(game.id, attacker.id, card.id, defender.id)

    assert game.pending_attack is not None
    assert game.pending_attack.attacker_id == attacker.id
    assert game.pending_attack.defender_id == defender.id
    assert game.pending_attack.damage == 5
    assert card in attacker.table_deck.cards
    game_repository.save.assert_called_once_with(game)


def test_end_turn_resolves_pending_attack_when_not_defended(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
) -> None:
    from domain.entities import PendingAttack

    logic, game_repository, _, _, deck_service, state_manager = game_logic

    attacker = make_player(nickname="attacker", cur_echo=3, hand_size=2)
    defender = make_player(nickname="defender", health=20)
    attacker.hand_deck.cards = []
    attacker.table_deck.cards = []
    attacker.draw_deck.cards = [make_card(title="d1"), make_card(title="d2")]

    game = make_game(
        host_user_id=uuid4(),
        players=[attacker, defender],
        cur_player_id=attacker.id,
        pending_attack=PendingAttack(
            attacker_id=attacker.id, defender_id=defender.id, damage=7
        ),
    )
    game_repository.get.return_value = game
    state_manager.validate_turn.return_value = True
    deck_service.draw.return_value = [make_card(title="d1"), make_card(title="d2")]

    logic.end_turn(game.id, attacker.id)

    assert defender.health == 13  # 20 - 7
    assert game.pending_attack is None
    game_repository.save.assert_called_once_with(game)


def test_defend_applies_defense_and_reduces_pending_damage(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
) -> None:
    from domain.entities import PendingAttack
    from domain.entities.card_type import CardType
    from domain.enums import CardAction, UsePattern

    logic, game_repository, _, card_logic, _, _ = game_logic

    attacker = make_player(nickname="attacker")
    defender = make_player(nickname="defender", health=20)
    def_card = make_card(power=3, echo=1)
    defender.hand_deck.cards.append(def_card)

    card_type = CardType(
        id=uuid4(), action=CardAction.DEF, usage_pattern=UsePattern.DISCARD
    )

    game = make_game(
        host_user_id=uuid4(),
        players=[attacker, defender],
        status=GameStatus.IN_PROGRESS,
        pending_attack=PendingAttack(
            attacker_id=attacker.id, defender_id=defender.id, damage=5
        ),
    )
    game_repository.get.return_value = game
    
    # Мокаем card_type_repository
    logic._card_type_repo = Mock()
    logic._card_type_repo.get.return_value = card_type
    
    card_logic.can_defend.return_value = True
    card_logic.apply_defense.return_value = 2  # 5 - 3 = 2 оставшегося урона

    logic.defend(game.id, defender.id, def_card.id)

    assert game.pending_attack is None
    assert defender.health == 18  # 20 - 2
    card_logic.can_defend.assert_called_once_with(defender, def_card, card_type)
    card_logic.apply_defense.assert_called_once_with(defender, def_card, card_type, 5)
    game_repository.save.assert_called_once_with(game)


def test_defend_raises_error_when_no_pending_attack(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
) -> None:
    logic, game_repository, *_ = game_logic

    defender = make_player(nickname="defender")
    def_card = make_card()

    game = make_game(
        host_user_id=uuid4(),
        players=[defender],
        status=GameStatus.IN_PROGRESS,
        pending_attack=None,
    )
    game_repository.get.return_value = game

    with pytest.raises(ValueError, match="No pending attack to defend against"):
        logic.defend(game.id, defender.id, def_card.id)


def test_defend_raises_error_when_not_the_defender(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
) -> None:
    from domain.entities import PendingAttack

    logic, game_repository, *_ = game_logic

    attacker = make_player(nickname="attacker")
    defender = make_player(nickname="defender")
    other_player = make_player(nickname="other")
    def_card = make_card()

    game = make_game(
        host_user_id=uuid4(),
        players=[attacker, defender, other_player],
        status=GameStatus.IN_PROGRESS,
        pending_attack=PendingAttack(
            attacker_id=attacker.id, defender_id=defender.id, damage=5
        ),
    )
    game_repository.get.return_value = game

    with pytest.raises(
        ValueError, match="You are not the target of the current attack"
    ):
        logic.defend(game.id, other_player.id, def_card.id)


def test_defend_raises_error_when_card_cannot_defend(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
) -> None:
    from domain.entities import PendingAttack
    from domain.entities.card_type import CardType
    from domain.enums import CardAction, UsePattern

    logic, game_repository, _, card_logic, _, _ = game_logic

    attacker = make_player(nickname="attacker")
    defender = make_player(nickname="defender")
    def_card = make_card()
    defender.hand_deck.cards.append(def_card)
    
    card_type = CardType(
        id=uuid4(), action=CardAction.DEF, usage_pattern=UsePattern.DISCARD
    )

    game = make_game(
        host_user_id=uuid4(),
        players=[attacker, defender],
        status=GameStatus.IN_PROGRESS,
        pending_attack=PendingAttack(
            attacker_id=attacker.id, defender_id=defender.id, damage=5
        ),
    )
    game_repository.get.return_value = game
    
    # Мокаем card_type_repository
    logic._card_type_repo = Mock()
    logic._card_type_repo.get.return_value = card_type
    
    card_logic.can_defend.return_value = False

    with pytest.raises(ValueError, match="This DEF card cannot be played as defense"):
        logic.defend(game.id, defender.id, def_card.id)


def test_apply_damage_respawns_at_default_health_when_killed(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
) -> None:
    from domain.player_health import DEFAULT_PLAYER_HEALTH

    logic, *_ = game_logic
    player = make_player(health=5)
    game = make_game(host_user_id=uuid4(), players=[player])

    logic._apply_damage(player, 10, game)

    assert player.health == DEFAULT_PLAYER_HEALTH


def test_play_heal_without_target_id_targets_self(
    game_logic: tuple[GameLogic, Mock, Mock, Mock, Mock, Mock],
    make_game: Callable[..., Game],
    make_player: Callable[..., Player],
    make_card: Callable[..., Card],
) -> None:
    from domain.entities.card_type import CardType
    from domain.enums import CardAction, UsePattern

    logic, game_repository, _, card_logic, _, state_manager = game_logic
    player = make_player(health=10)
    card = make_card(power=3, echo=0)
    player.hand_deck.cards.append(card)

    card_type = CardType(
        id=uuid4(),
        action=CardAction.HEAL,
        usage_pattern=UsePattern.REG,
        color="green",
    )
    card.card_type_id = card_type.id

    game = make_game(
        host_user_id=uuid4(),
        players=[player],
        status=GameStatus.IN_PROGRESS,
        cur_player_id=player.id,
    )
    game_repository.get.return_value = game
    state_manager.validate_turn.return_value = True
    card_logic.can_be_played.return_value = True
    card_logic.apply_effect.return_value = 0

    logic._card_type_repo = Mock()
    logic._card_type_repo.get.return_value = card_type

    logic.play_card(game.id, player.id, card.id)

    card_logic.apply_effect.assert_called_once_with(
        player, card, card_type, player, logic._deck_service
    )
