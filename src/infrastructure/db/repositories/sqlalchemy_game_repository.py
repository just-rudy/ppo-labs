from uuid import UUID

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from application.interfaces.game_repository import GameRepository
from domain.entities import Card, Deck, Game, Player
from domain.enums import DeckType
from infrastructure.db.exceptions import (
    EntityNotFoundError,
    EntityValidationError,
    PersistenceError,
)
from infrastructure.db.mappers.card_mapper import CardMapper
from infrastructure.db.mappers.game_mapper import GameMapper
from infrastructure.db.mappers.image_mapper import ImageMapper
from infrastructure.db.mappers.player_mapper import PlayerMapper
from infrastructure.db.models import (
    CardModel,
    DeckCardModel,
    DeckModel,
    GameModel,
    ImageModel,
    PlayerModel,
)


class SqlAlchemyGameRepository(GameRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def _sync_image(self, card: Card) -> None:
        if card.image is None:
            raise EntityValidationError("card image must be provided")
        if card.image.id != card.image_id:
            raise EntityValidationError("card image id must match image.id")

        image_model = self._session.get(ImageModel, card.image_id)
        if image_model is None:
            image_model = ImageMapper.to_model(card.image)
            self._session.add(image_model)
            return

        image_model.title = card.image.title
        image_model.file = card.image.file

    def _sync_deck(
        self,
        deck: Deck,
        deck_type: DeckType,
        game_id: UUID | None,
        player_id: UUID | None,
        existing_decks: dict[UUID, DeckModel],
    ) -> UUID:
        deck_model = existing_decks.get(deck.id)
        if deck_model is None:
            deck_model = DeckModel(id=deck.id)
            self._session.add(deck_model)

        deck_model.type = deck_type.value
        deck_model.game_id = game_id
        deck_model.player_id = player_id
        deck_model.if_open = deck.if_open

        deck_model.deck_cards = []
        self._session.flush()

        for position, card in enumerate(deck.cards):
            self._sync_image(card)
            card_model = self._session.get(CardModel, card.id)
            if card_model is None:
                card_model = CardMapper.to_model(card)
                self._session.add(card_model)
            else:
                card_model.title = card.title
                card_model.creature = card.creature
                card_model.card_type_id = card.card_type_id
                card_model.image_id = card.image_id
                card_model.power = card.power
                card_model.echo = card.echo
                card_model.cost = card.cost
                card_model.cool_points = card.cool_points

            deck_model.deck_cards.append(
                DeckCardModel(
                    card=card_model,
                    position=position,
                )
            )

        return deck.id

    def _load_deck(self, deck_model: DeckModel) -> Deck:
        cards: list[Card] = []
        for deck_card in deck_model.deck_cards:
            card_model = deck_card.card
            if card_model is None:
                raise EntityNotFoundError(
                    f"card {deck_card.card_id} referenced by deck "
                    f"{deck_model.id} not found"
                )
            cards.append(CardMapper.to_domain(card_model))

        return Deck(
            id=deck_model.id,
            type=DeckType(deck_model.type),
            if_open=deck_model.if_open,
            cards=cards,
        )

    def save(self, game: Game) -> None:
        try:
            model = self._session.get(GameModel, game.id)
            if model is None:
                model = GameMapper.to_model(game)
                self._session.add(model)
                self._session.flush()
            else:
                model.host_user_id = game.host_user_id
                model.name = game.name
                model.status = game.status.value
                model.cur_turn = game.cur_turn
                model.cur_player_id = game.cur_player_id
                model.winner_id = game.winner_id
                model.pending_attacker_id = (
                    game.pending_attack.attacker_id if game.pending_attack else None
                )
                model.pending_defender_id = (
                    game.pending_attack.defender_id if game.pending_attack else None
                )
                model.pending_damage = (
                    game.pending_attack.damage if game.pending_attack else None
                )

            existing_players = {
                player_model.id: player_model
                for player_model in self._session.query(PlayerModel)
                .filter(PlayerModel.game_id == game.id)
                .all()
            }
            players_ids = set()

            for player in game.players:
                players_ids.add(player.id)
                player_model = existing_players.get(player.id)
                if player_model is None:
                    player_model = PlayerModel(
                        id=player.id,
                        game_id=game.id,
                        user_id=player.user_id,
                        nickname=player.nickname,
                        turn_order=player.turn_order,
                        health=player.health,
                        base_echo=player.base_echo,
                        cur_echo=player.cur_echo,
                        hand_size=player.hand_size,
                    )
                    self._session.add(player_model)
                else:
                    PlayerMapper.update_model(player_model, player)

            for player_id, player_model in existing_players.items():
                if player_id not in players_ids:
                    self._session.delete(player_model)

            existing_decks = {
                deck_model.id: deck_model
                for deck_model in self._session.query(DeckModel)
                .options(selectinload(DeckModel.deck_cards))
                .filter(DeckModel.game_id == game.id)
                .all()
            }
            deck_ids = {
                self._sync_deck(
                    game.market_deck,
                    DeckType.MARKET,
                    game.id,
                    None,
                    existing_decks,
                ),
                self._sync_deck(
                    game.game_deck,
                    DeckType.DECK,
                    game.id,
                    None,
                    existing_decks,
                ),
                self._sync_deck(
                    game.banish_deck,
                    DeckType.BANISH,
                    game.id,
                    None,
                    existing_decks,
                ),
            }

            for player in game.players:
                deck_ids.add(
                    self._sync_deck(
                        player.draw_deck,
                        DeckType.DRAW,
                        game.id,
                        player.id,
                        existing_decks,
                    )
                )
                deck_ids.add(
                    self._sync_deck(
                        player.hand_deck,
                        DeckType.HAND,
                        game.id,
                        player.id,
                        existing_decks,
                    )
                )
                deck_ids.add(
                    self._sync_deck(
                        player.table_deck,
                        DeckType.TABLE,
                        game.id,
                        player.id,
                        existing_decks,
                    )
                )
                deck_ids.add(
                    self._sync_deck(
                        player.discard_deck,
                        DeckType.DISCARD,
                        game.id,
                        player.id,
                        existing_decks,
                    )
                )

            for deck_id, deck_model in existing_decks.items():
                if deck_id not in deck_ids:
                    self._session.query(DeckCardModel).filter(
                        DeckCardModel.deck_id == deck_id
                    ).delete()
                    self._session.delete(deck_model)

            self._session.commit()

        # except IntegrityError as exc:
        #     self._session.rollback()
        #     raise PersistenceError(
        #         "failed to save game - integrity constraint violated"
        #     ) from exc

        except IntegrityError as exc:
            self._session.rollback()
            print("REAL DB ERROR:", exc)
            raise PersistenceError(
                "failed to save game - integrity constraint violated"
            ) from exc

        except SQLAlchemyError as exc:
            self._session.rollback()
            raise PersistenceError("failed to save game") from exc

    def get(self, game_id: UUID) -> Game:
        model = self._session.get(GameModel, game_id)
        if model is None:
            raise EntityNotFoundError(f"Game {game_id} not found")

        game = GameMapper.to_domain(model)
        player_models = (
            self._session.query(PlayerModel)
            .options(
                selectinload(PlayerModel.decks),
            )
            .filter(PlayerModel.game_id == game.id)
            .order_by(PlayerModel.turn_order.asc())
            .all()
        )
        game.players = [
            PlayerMapper.to_domain(player_model) for player_model in player_models
        ]
        players_by_id: dict[UUID, Player] = {
            player.id: player for player in game.players
        }

        deck_models = (
            self._session.query(DeckModel)
            .options(
                selectinload(DeckModel.deck_cards)
                .selectinload(DeckCardModel.card)
                .selectinload(CardModel.image),
            )
            .filter(DeckModel.game_id == game.id)
            .all()
        )

        for deck_model in deck_models:
            deck = self._load_deck(deck_model)
            if deck_model.player_id is None:
                if deck.type == DeckType.MARKET:
                    game.market_deck = deck
                elif deck.type == DeckType.BANISH:
                    game.banish_deck = deck
                else:
                    game.game_deck = deck
                continue

            player = players_by_id.get(deck_model.player_id)
            if player is None:
                continue

            if deck.type == DeckType.DRAW:
                player.draw_deck = deck
            elif deck.type == DeckType.HAND:
                player.hand_deck = deck
            elif deck.type == DeckType.TABLE:
                player.table_deck = deck
            elif deck.type == DeckType.DISCARD:
                player.discard_deck = deck

        return game

    def delete(self, game_id: UUID) -> None:
        model = self._session.get(GameModel, game_id)
        if model is None:
            raise EntityNotFoundError(f"game {game_id} not found")

        try:
            self._session.query(PlayerModel).filter(
                PlayerModel.game_id == game_id
            ).delete()
            self._session.delete(model)
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise PersistenceError("failed to delete game") from exc

    def exists(self, game_id: UUID) -> bool:
        return self._session.get(GameModel, game_id) is not None

    def list_all(self) -> list[Game]:
        """Возвращает краткий список всех игр (без колод и игроков)."""
        models = self._session.query(GameModel).order_by(GameModel.id).all()
        games = []
        for model in models:
            game = GameMapper.to_domain(model)
            # Загружаем только игроков (без колод) для подсчёта
            player_models = (
                self._session.query(PlayerModel)
                .filter(PlayerModel.game_id == model.id)
                .all()
            )
            game.players = [PlayerMapper.to_domain(pm) for pm in player_models]
            games.append(game)
        return games

    def get_by_name(self, name: str) -> "Game | None":
        model = self._session.query(GameModel).filter(GameModel.name == name).first()
        if model is None:
            return None
        return self.get(model.id)
