from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.db.base import Base

if TYPE_CHECKING:
    from infrastructure.db.models.card_model import CardModel
    from infrastructure.db.models.deck_model import DeckModel


class DeckCardModel(Base):
    __tablename__ = "deck_cards"
    __table_args__ = (UniqueConstraint("deck_id", "position", name="uq_deck_position"),)

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    deck_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("decks.id"),
        nullable=False,
        index=True,
    )
    card_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cards.id"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    deck: Mapped["DeckModel"] = relationship(
        "DeckModel",
        back_populates="deck_cards",
    )
    card: Mapped["CardModel"] = relationship(
        "CardModel",
        back_populates="deck_cards",
    )
