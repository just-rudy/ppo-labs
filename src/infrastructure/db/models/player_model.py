from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.db.base import Base

if TYPE_CHECKING:
    from infrastructure.db.models.deck_model import DeckModel
    from infrastructure.db.models.game_model import GameModel
    from infrastructure.db.models.user_model import UserModel


class PlayerModel(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("game_id", "user_id", name="uq_players_game_user"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    game_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    turn_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    health: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    base_echo: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cur_echo: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hand_size: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    # memos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # color: Mapped[str] = mapped_column(String(20), nullable=False)
    game: Mapped["GameModel"] = relationship(
        "GameModel",
        back_populates="players",
        foreign_keys=[game_id],
    )
    user: Mapped["UserModel"] = relationship("UserModel")
    decks: Mapped[list["DeckModel"]] = relationship(
        "DeckModel",
        back_populates="player",
        cascade="all, delete-orphan",
    )
