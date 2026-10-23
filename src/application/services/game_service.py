import random
import re
from typing import TYPE_CHECKING
from uuid import UUID

from application.dto.requests import CreateGameRequest
from application.interfaces.card_repository import CardRepository
from application.interfaces.card_type_repository import CardTypeRepository
from application.interfaces.game_repository import GameRepository
from application.interfaces.user_repository import UserRepository
from application.services.card_logic import CardLogic
from application.services.deck_service import DeckService
from application.services.game_logic import GameLogic
from application.services.game_state_manager import GameStateManager
from domain.entities import Card, Game

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class GameAppService:
    def __init__(
        self,
        game_repository: GameRepository,
        user_repository: UserRepository,
        card_logic: CardLogic,
        deck_service: DeckService,
        game_state_manager: GameStateManager,
        card_repository: CardRepository,
        default_market_size: int = 5,
        card_type_repository: CardTypeRepository | None = None,
        db_session: "Session | None" = None,
    ) -> None:
        self._game_repository = game_repository
        self._card_repository = card_repository
        self._default_market_size = default_market_size
        self._db_session = db_session
        self._logic = GameLogic(
            game_repository=game_repository,
            user_repository=user_repository,
            card_logic=card_logic,
            deck_service=deck_service,
            game_state_manager=game_state_manager,
            card_type_repository=card_type_repository,
        )

    def create_new_game(self, request: CreateGameRequest) -> Game:
        name = self._resolve_game_name(request.name)
        return self._logic.create_game(request.host_user_id, name=name)

    def _resolve_game_name(self, requested: str | None) -> str:
        """Валидирует имя (латиница + цифры) или генерирует game-xxx."""
        if requested and requested.strip():
            clean = requested.strip()
            if not re.fullmatch(r"[A-Za-z0-9\-]+", clean):
                raise ValueError(
                    "Game name must contain only Latin letters, digits and hyphen"
                )
            if self._game_repository.get_by_name(clean) is not None:
                raise ValueError("Game name already taken")
            return clean
        for _ in range(20):
            candidate = f"game-{random.randint(100, 999)}"
            if self._game_repository.get_by_name(candidate) is None:
                return candidate
        return f"game-{random.randint(1000, 9999)}"

    def resolve_game_id(self, game_ref: str) -> UUID:
        ref = game_ref.strip()
        if not ref:
            raise ValueError("Game reference is required")

        try:
            game_id = UUID(ref)
        except ValueError:
            game = self._game_repository.get_by_name(ref)
            if game is None:
                raise ValueError(f"Game '{ref}' not found") from None
            return game.id

        if not self._game_repository.exists(game_id):
            raise ValueError("Game not found")
        return game_id

    def list_joinable_games(self) -> list[Game]:
        from domain.enums import GameStatus

        return [
            game
            for game in self._game_repository.list_all()
            if game.status in (GameStatus.CREATED, GameStatus.IN_PROGRESS)
        ]

    def list_games(self) -> list[Game]:
        return self._game_repository.list_all()

    def get_game(self, game_id: UUID) -> Game:
        return self._game_repository.get(game_id)

    def delete_game(self, game_id: UUID) -> None:
        self._game_repository.delete(game_id)

    def join_game(self, game_id: UUID, user_id: UUID) -> Game:
        self._logic.add_player(game_id, user_id)
        return self._game_repository.get(game_id)

    def start_game(self, game_id: UUID) -> Game:
        self._generate_decks(game_id)
        self._logic.start_game(game_id)
        return self._game_repository.get(game_id)

    def _generate_decks(self, game_id: UUID) -> None:
        game = self._game_repository.get(game_id)

        if not game.players:
            raise ValueError("No players in game")

        cards = self._generate_cards(50)
        random.shuffle(cards)

        game.market_deck.cards = cards[: self._default_market_size]

        index = self._default_market_size
        for player in game.players:
            player.draw_deck.cards = cards[index : index + 10]
            player.hand_deck.cards = player.draw_deck.cards[: player.hand_size]
            player.draw_deck.cards = player.draw_deck.cards[player.hand_size :]
            player.discard_deck.cards = []
            player.table_deck.cards = []
            index += 10

        game.game_deck.cards = cards[index:]
        self._game_repository.save(game)

    def _refill_market(self, game: Game) -> None:
        missing_cards_count = self._default_market_size - len(game.market_deck.cards)
        if missing_cards_count <= 0:
            return

        cards = game.game_deck.cards[:missing_cards_count]
        game.market_deck.cards.extend(cards)
        del game.game_deck.cards[: len(cards)]

    def _generate_cards(self, count: int) -> list[Card]:
        all_cards = self._card_repository.list_all()
        if len(all_cards) < count:
            msg = (
                f"Not enough cards in database: need {count}, "
                f"have {len(all_cards)}. Run `make db-seed` to populate cards."
            )
            raise ValueError(msg)
        return random.sample(all_cards, count)

    def play_card(
        self,
        game_id: UUID,
        player_id: UUID,
        card_id: UUID,
        target_id: UUID | None = None,
    ) -> Game:
        self._logic.play_card(game_id, player_id, card_id, target_id=target_id)
        return self._game_repository.get(game_id)

    def defend(self, game_id: UUID, defender_id: UUID, card_id: UUID) -> Game:
        self._logic.defend(game_id, defender_id, card_id)
        return self._game_repository.get(game_id)

    def skip_defend(self, game_id: UUID, player_id: UUID) -> Game:
        self._logic.skip_defend(game_id, player_id)
        return self._game_repository.get(game_id)

    def buy_card(self, game_id: UUID, player_id: UUID, card_id: UUID) -> Game:
        """Покупка карты с рынка.

        В PostgreSQL использует хранимую процедуру purchase_card(),
        которая атомарно проверяет баланс эхо и списывает стоимость карты.
        В тестах без сессии выполняет проверки и обновление через доменную логику.
        """
        game = self._game_repository.get(game_id)
        player = self._logic._get_player(game, player_id)

        if game.status.value != "in_progress":
            from domain.enums import GameStatus
            if game.status != GameStatus.IN_PROGRESS:
                raise ValueError("Game not in progress")

        if not self._logic._state.validate_turn(game, player_id):
            raise ValueError("Another player's turn")

        card = self._logic._get_card(game.market_deck, card_id)

        if not self._logic._card_logic.can_purchase(player, card):
            raise ValueError("Card can't be purchased")

        if self._db_session is not None:
            # Используем хранимую процедуру — атомарное списание в БД
            from sqlalchemy import text
            try:
                self._db_session.execute(
                    text("SELECT purchase_card(:player_id, :card_id)"),
                    {"player_id": str(player_id), "card_id": str(card_id)},
                )
                self._db_session.flush()
            except Exception as exc:
                self._db_session.rollback()
                raise ValueError(str(exc)) from exc
            # Синхронизируем доменную модель с тем, что сделала процедура
            player.cur_echo -= card.cost
        else:
            # В тестах без сессии обновляем доменную модель напрямую
            player.cur_echo -= card.cost

        player.discard_deck.cards.append(card)
        game.market_deck.cards.remove(card)
        self._game_repository.save(game)
        return self._game_repository.get(game_id)

    def end_turn(self, game_id: UUID, player_id: UUID) -> Game:
        self._logic.end_turn(game_id, player_id)
        game = self._game_repository.get(game_id)
        self._refill_market(game)
        self._game_repository.save(game)
        return game

    def finish_game(self, game_id: UUID, player_id: UUID) -> Game:
        self._logic.finish_game(game_id, player_id)
        return self._game_repository.get(game_id)
