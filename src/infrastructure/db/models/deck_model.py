from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domain.enums import DeckType
from infrastructure.db.base import Base

if TYPE_CHECKING:
    from infrastructure.db.models.deck_card_model import DeckCardModel
    from infrastructure.db.models.game_model import GameModel
    from infrastructure.db.models.player_model import PlayerModel


class DeckModel(Base):
    __tablename__ = "decks"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default=DeckType.DRAW)
    game_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("games.id"),
        nullable=True,
        index=True,
    )
    player_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("players.id"),
        nullable=True,
        index=True,
    )
    if_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    game: Mapped["GameModel | None"] = relationship(
        "GameModel",
        back_populates="decks",
    )
    player: Mapped["PlayerModel | None"] = relationship(
        "PlayerModel",
        back_populates="decks",
    )
    deck_cards: Mapped[list["DeckCardModel"]] = relationship(
        "DeckCardModel",
        back_populates="deck",
        cascade="all, delete-orphan",
        order_by="DeckCardModel.position",
    )
