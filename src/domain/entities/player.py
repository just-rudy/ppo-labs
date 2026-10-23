from dataclasses import dataclass, field
from uuid import UUID, uuid4

from domain.player_health import DEFAULT_PLAYER_HEALTH

from .deck import Deck


@dataclass
class Player:
    id: UUID
    user_id: UUID
    nickname: str
    turn_order: int = 0
    health: int = DEFAULT_PLAYER_HEALTH
    base_echo: int = 0
    cur_echo: int = 0
    hand_size: int = 5
    # decks will be moved later, here for simplicity
    # Player.draw_deck в БД соответствует записи Decks,
    # где owner_player_id = Player.id и type = 'draw'
    draw_deck: Deck = field(default_factory=lambda: Deck(id=uuid4()))
    hand_deck: Deck = field(default_factory=lambda: Deck(id=uuid4()))
    table_deck: Deck = field(default_factory=lambda: Deck(id=uuid4()))
    discard_deck: Deck = field(default_factory=lambda: Deck(id=uuid4()))
