import random
from uuid import UUID, uuid4

from application.interfaces.card_type_repository import CardTypeRepository
from application.interfaces.game_repository import GameRepository
from application.interfaces.user_repository import UserRepository
from application.services.card_logic import CardLogic
from application.services.deck_service import DeckService
from application.services.game_state_manager import GameStateManager
from domain.entities import Card, CardType, Deck, Game, PendingAttack, Player
from domain.enums import CardAction, GameStatus, UserRole
from domain.player_health import DEFAULT_PLAYER_HEALTH, health_after_death


class GameLogic:
    def __init__(
        self,
        game_repository: GameRepository,
        user_repository: UserRepository,
        card_logic: CardLogic,
        deck_service: DeckService,
        game_state_manager: GameStateManager,
        card_type_repository: CardTypeRepository | None = None,
    ) -> None:
        self._repo = game_repository
        self._us_repo = user_repository
        self._card_logic = card_logic
        self._deck_service = deck_service
        self._state = game_state_manager
        self._card_type_repo = card_type_repository

    def _get_player(self, game: Game, player_id: UUID) -> Player:
        for player in game.players:
            if player.id == player_id:
                return player
        raise ValueError("Player not found in game")

    def _get_card(self, deck: Deck, card_id: UUID) -> Card:
        for card in deck.cards:
            if card.id == card_id:
                return card
        raise ValueError("Card not in deck")

    def _player_cards(self, player: Player) -> list[Card]:
        return [
            *player.draw_deck.cards,
            *player.hand_deck.cards,
            *player.table_deck.cards,
            *player.discard_deck.cards,
        ]

    def _apply_damage(self, player: Player, damage: int, game: Game) -> None:
        if damage <= 0:
            return
        player.health -= damage
        if player.health <= 0:
            player.health = health_after_death()

    def _resolve_heal_target(
        self,
        player: Player,
        card_type: CardType | None,
        target: Player | None,
    ) -> Player | None:
        if (
            card_type is not None
            and card_type.action == CardAction.HEAL
            and target is None
        ):
            return player
        return target

    def _determine_winner(self, game: Game) -> Player:
        if not game.players:
            raise ValueError("No players in the game")

        def ranking(player: Player) -> tuple[int, int, int, str, str]:
            cards = self._player_cards(player)
            cool_points = sum(card.cool_points for card in cards)
            cards_count = len(cards)
            return (
                cool_points,
                cards_count,
                -player.turn_order,
                player.nickname,
                str(player.id),
            )

        return max(game.players, key=ranking)

    def create_game(self, host_user_id: UUID, name: str = "") -> Game:
        game = Game(id=uuid4(), host_user_id=host_user_id, name=name)
        self._repo.save(game)
        return game

    def start_game(self, game_id: UUID) -> None:
        game = self._repo.get(game_id)

        if game.status == GameStatus.IN_PROGRESS:
            raise ValueError("Game already in progress")

        game.status = GameStatus.IN_PROGRESS
        game.winner_id = None
        game = self.order_player_turns(game)

        if not game.players:
            raise ValueError("No players in the game")

        game.cur_turn = 0
        game.cur_player_id = game.players[0].id

        self._repo.save(game)

    def order_player_turns(self, game: Game) -> Game:
        random.shuffle(game.players)
        for i, player in enumerate(game.players):
            player.turn_order = i
        return game

    def add_player(self, game_id: UUID, user_id: UUID) -> Player:
        game = self._repo.get(game_id)

        if any(player.user_id == user_id for player in game.players):
            raise ValueError("User is already in the game")

        user = self._us_repo.get(user_id)

        player = Player(
            id=uuid4(),
            user_id=user_id,
            nickname=user.username,
            health=DEFAULT_PLAYER_HEALTH,
        )
        if user.role == UserRole.AUTHENTICATED:
            user.role = UserRole.PLAYER
            self._us_repo.save(user)

        game.players.append(player)
        self._repo.save(game)
        return player

    def buy_card(self, game_id: UUID, player_id: UUID, card_id: UUID) -> None:
        game = self._repo.get(game_id)
        player = self._get_player(game, player_id)

        if game.status != GameStatus.IN_PROGRESS:
            raise ValueError("Game not in progress")

        if not self._state.validate_turn(game, player_id):
            raise ValueError("Another player's turn")

        card = self._get_card(game.market_deck, card_id)

        if not self._card_logic.can_purchase(player, card):
            raise ValueError("Card can't be purchased")

        player.cur_echo -= card.cost
        player.discard_deck.cards.append(card)
        game.market_deck.cards.remove(card)

        self._repo.save(game)

    def play_card(
        self,
        game_id: UUID,
        player_id: UUID,
        card_id: UUID,
        target_id: UUID | None = None,
    ) -> None:
        game = self._repo.get(game_id)
        player = self._get_player(game, player_id)

        if game.status != GameStatus.IN_PROGRESS:
            raise ValueError("Game not in progress")

        if not self._state.validate_turn(game, player_id):
            raise ValueError("Another player's turn")

        card = self._get_card(player.hand_deck, card_id)

        if not self._card_logic.can_be_played(player, card):
            raise ValueError("Card can't be played")

        card_type = None
        if self._card_type_repo is not None:
            card_type = self._card_type_repo.get(card.card_type_id)

        # DEF нельзя разыгрывать в свой ход — только через /defend
        if card_type is not None and card_type.action == CardAction.DEF:
            raise ValueError(
                "DEF card can only be played as a reaction to an attack via /defend"
            )

        target: Player | None = None
        if target_id is not None:
            target = self._get_player(game, target_id)

        target = self._resolve_heal_target(player, card_type, target)

        damage = self._card_logic.apply_effect(
            player, card, card_type, target, self._deck_service
        )

        player.hand_deck.cards.remove(card)
        player.table_deck.cards.append(card)

        # ATTACK: урон не применяется сразу — ждём реакции защитника
        if damage > 0 and target is not None:
            game.pending_attack = PendingAttack(
                attacker_id=player_id,
                defender_id=target.id,
                damage=damage,
            )

        self._repo.save(game)

    def defend(
        self,
        game_id: UUID,
        defender_id: UUID,
        card_id: UUID,
    ) -> None:
        """Защитник разыгрывает DEF карту в ответ на pending_attack."""
        game = self._repo.get(game_id)

        if game.status != GameStatus.IN_PROGRESS:
            raise ValueError("Game not in progress")

        if game.pending_attack is None:
            raise ValueError("No pending attack to defend against")

        if game.pending_attack.defender_id != defender_id:
            raise ValueError("You are not the target of the current attack")

        defender = self._get_player(game, defender_id)
        card = self._get_card(defender.hand_deck, card_id)

        card_type = None
        if self._card_type_repo is not None:
            card_type = self._card_type_repo.get(card.card_type_id)

        if card_type is None or card_type.action != CardAction.DEF:
            raise ValueError("Only DEF cards can be used to defend")

        if not self._card_logic.can_defend(defender, card, card_type):
            raise ValueError("This DEF card cannot be played as defense")

        remaining = self._card_logic.apply_defense(
            defender, card, card_type, game.pending_attack.damage
        )

        if remaining > 0:
            self._apply_damage(defender, remaining, game)

        game.pending_attack = None
        self._repo.save(game)

    def resolve_pending_attack(self, game: Game) -> None:
        """Применяет накопленный урон если защитник не ответил. Вызывается при end_turn."""
        if game.pending_attack is None:
            return
        defender = self._get_player(game, game.pending_attack.defender_id)
        self._apply_damage(defender, game.pending_attack.damage, game)
        game.pending_attack = None

    def skip_defend(self, game_id: UUID, defender_id: UUID) -> None:
        """Защитник сознательно отказывается от защиты — урон применяется сразу."""
        game = self._repo.get(game_id)

        if game.status != GameStatus.IN_PROGRESS:
            raise ValueError("Game not in progress")

        if game.pending_attack is None:
            raise ValueError("No pending attack to skip")

        if game.pending_attack.defender_id != defender_id:
            raise ValueError("You are not the target of the current attack")

        defender = self._get_player(game, defender_id)
        self._apply_damage(defender, game.pending_attack.damage, game)
        game.pending_attack = None
        self._repo.save(game)

    def end_turn(self, game_id: UUID, player_id: UUID) -> None:
        game = self._repo.get(game_id)

        if not self._state.validate_turn(game, player_id):
            raise ValueError("Another player's turn")

        # Если атакующий завершает ход не дождавшись защиты — урон применяется
        self.resolve_pending_attack(game)

        player = self._get_player(game, player_id)
        player.cur_echo = player.base_echo
        player.discard_deck.cards.extend(player.hand_deck.cards)
        player.discard_deck.cards.extend(player.table_deck.cards)
        player.hand_deck.cards.clear()
        player.table_deck.cards.clear()

        if len(player.draw_deck.cards) < player.hand_size:
            player.draw_deck.cards.extend(player.discard_deck.cards)
            player.discard_deck.cards.clear()
            self._deck_service.shuffle(player.draw_deck)

        draw_count = min(player.hand_size, len(player.draw_deck.cards))
        if draw_count > 0:
            player.hand_deck.cards.extend(
                self._deck_service.draw(player.draw_deck, draw_count)
            )

        self._state.next_turn(game)
        self._repo.save(game)

    def finish_game(self, game_id: UUID, player_id: UUID) -> None:
        game = self._repo.get(game_id)
        self._get_player(game, player_id)

        if game.status == GameStatus.FINISHED:
            raise ValueError("Game already finished")

        winner = self._determine_winner(game)
        game.status = GameStatus.FINISHED
        game.cur_player_id = None
        game.winner_id = winner.id
        self._repo.save(game)
