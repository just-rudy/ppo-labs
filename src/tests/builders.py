from __future__ import annotations

from uuid import UUID, uuid4

from domain.entities import Card, CardType, Deck, Game, Image, Player, User
from domain.enums import CardAction, DeckType, GameStatus, UsePattern, UserRole


class CardBuilder:
    def __init__(self) -> None:
        self._id = uuid4()
        self._title = "Test card"
        self._creature = "test creature"
        self._card_type_id = uuid4()
        self._power = 1
        self._echo = 1
        self._cost = 3
        self._cool_points = 0
        self._image = Image(id=uuid4(), title="Test image", file="cards/test.png")

    def with_cost(self, cost: int) -> CardBuilder:
        self._cost = cost
        return self

    def with_title(self, title: str) -> CardBuilder:
        self._title = title
        return self

    def with_power(self, power: int) -> CardBuilder:
        self._power = power
        return self

    def with_echo(self, echo: int) -> CardBuilder:
        self._echo = echo
        return self

    def with_cool_points(self, cool_points: int) -> CardBuilder:
        self._cool_points = cool_points
        return self

    def with_card_type_id(self, card_type_id: UUID) -> CardBuilder:
        self._card_type_id = card_type_id
        return self

    def build(self) -> Card:
        return Card(
            id=self._id,
            title=self._title,
            creature=self._creature,
            card_type_id=self._card_type_id,
            image_id=self._image.id,
            power=self._power,
            echo=self._echo,
            cost=self._cost,
            cool_points=self._cool_points,
            image=self._image,
        )


class PlayerBuilder:
    def __init__(self) -> None:
        self._draw_deck = Deck(id=uuid4(), type=DeckType.DRAW)
        self._hand_deck = Deck(id=uuid4(), type=DeckType.HAND)
        self._table_deck = Deck(id=uuid4(), type=DeckType.TABLE)
        self._discard_deck = Deck(id=uuid4(), type=DeckType.DISCARD)
        self._id = uuid4()
        self._user_id = uuid4()
        self._nickname = "player"
        self._turn_order = 0
        self._health = 20
        self._base_echo = 0
        self._cur_echo = 0
        self._hand_size = 5

    def with_current_echo(self, cur_echo: int) -> PlayerBuilder:
        self._cur_echo = cur_echo
        return self

    def with_base_echo(self, base_echo: int) -> PlayerBuilder:
        self._base_echo = base_echo
        return self

    def with_turn_order(self, turn_order: int) -> PlayerBuilder:
        self._turn_order = turn_order
        return self

    def with_hand_size(self, hand_size: int) -> PlayerBuilder:
        self._hand_size = hand_size
        return self

    def with_health(self, health: int) -> PlayerBuilder:
        self._health = health
        return self

    def with_hand(self, cards: list[Card]) -> PlayerBuilder:
        self._hand_deck.cards = cards
        return self

    def with_draw_pile(self, cards: list[Card]) -> PlayerBuilder:
        self._draw_deck.cards = cards
        return self

    def with_table(self, cards: list[Card]) -> PlayerBuilder:
        self._table_deck.cards = cards
        return self

    def build(self) -> Player:
        return Player(
            id=self._id,
            user_id=self._user_id,
            nickname=self._nickname,
            turn_order=self._turn_order,
            health=self._health,
            base_echo=self._base_echo,
            cur_echo=self._cur_echo,
            hand_size=self._hand_size,
            draw_deck=self._draw_deck,
            hand_deck=self._hand_deck,
            table_deck=self._table_deck,
            discard_deck=self._discard_deck,
        )


class ObjectMother:
    @staticmethod
    def attack_card_type() -> CardType:
        return CardType(
            id=uuid4(), action=CardAction.ATTACK, usage_pattern=UsePattern.REG
        )

    @staticmethod
    def def_card_type() -> CardType:
        return CardType(
            id=uuid4(), action=CardAction.DEF, usage_pattern=UsePattern.DISCARD
        )

    @staticmethod
    def heal_card_type() -> CardType:
        return CardType(
            id=uuid4(), action=CardAction.HEAL, usage_pattern=UsePattern.REG
        )

    @staticmethod
    def authenticated_user(username: str = "alice") -> User:
        return User(id=uuid4(), username=username, role=UserRole.AUTHENTICATED)

    @staticmethod
    def game_with_players(players: list[Player]) -> Game:
        return Game(
            id=uuid4(),
            host_user_id=uuid4(),
            status=GameStatus.IN_PROGRESS,
            players=players,
            cur_player_id=players[0].id if players else None,
            market_deck=Deck(id=uuid4(), type=DeckType.MARKET, if_open=True),
            game_deck=Deck(id=uuid4(), type=DeckType.DECK),
            banish_deck=Deck(id=uuid4(), type=DeckType.BANISH),
        )
