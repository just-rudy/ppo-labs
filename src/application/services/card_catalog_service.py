from uuid import UUID, uuid4

from application.interfaces.card_repository import CardRepository
from application.interfaces.card_type_repository import CardTypeRepository
from application.services.card_factory import _build_image
from domain.entities import Card
from infrastructure.db.exceptions import EntityNotFoundError, EntityValidationError

# Фрагменты сообщений PostgreSQL-триггера, которые нужно пробросить как 400
_TRIGGER_EXCEPTION_MARKERS = (
    "card cost must be between",
    "card power must be positive",
    "power for buff_",
    "buff_* card must have",
    "cool_points must be between",
    "card must have a card type",
)


def _is_trigger_error(message: str) -> bool:
    lower = message.lower()
    return any(marker in lower for marker in _TRIGGER_EXCEPTION_MARKERS)


class CardCatalogService:
    def __init__(
        self,
        card_repository: CardRepository,
        card_type_repository: CardTypeRepository,
    ) -> None:
        self._cards = card_repository
        self._card_types = card_type_repository

    def create_card(
        self,
        *,
        title: str,
        creature: str,
        card_type_id: UUID,
        power: int,
        echo: int,
        cost: int,
        cool_points: int,
    ) -> Card:
        title = title.strip()
        creature = creature.strip()
        if not title:
            raise EntityValidationError("card title must not be empty")
        if not creature:
            raise EntityValidationError("card creature must not be empty")
        if self._cards.find_by_title(title) is not None:
            raise EntityValidationError("card with this title already exists")

        self._card_types.get(card_type_id)

        image = _build_image(title)
        card = Card(
            id=uuid4(),
            title=title,
            creature=creature,
            card_type_id=card_type_id,
            image_id=image.id,
            power=power,
            echo=echo,
            cost=cost,
            cool_points=cool_points,
            image=image,
        )
        try:
            self._cards.save(card)
        except EntityValidationError:
            raise
        except Exception as exc:
            msg = str(exc)
            if _is_trigger_error(msg):
                raise EntityValidationError(msg) from exc
            raise
        return self._load_card(card.id)

    def update_card(
        self,
        card_id: UUID,
        *,
        title: str,
        creature: str,
        card_type_id: UUID,
        power: int,
        echo: int,
        cost: int,
        cool_points: int,
    ) -> Card:
        title = title.strip()
        creature = creature.strip()
        if not title:
            raise EntityValidationError("card title must not be empty")
        if not creature:
            raise EntityValidationError("card creature must not be empty")

        card = self._cards.get(card_id)
        existing = self._cards.find_by_title(title)
        if existing is not None and existing.id != card_id:
            raise EntityValidationError("card with this title already exists")

        self._card_types.get(card_type_id)

        card.title = title
        card.creature = creature
        card.card_type_id = card_type_id
        card.power = power
        card.echo = echo
        card.cost = cost
        card.cool_points = cool_points
        if card.image is not None:
            card.image.title = title

        try:
            self._cards.save(card)
        except EntityValidationError:
            raise
        except Exception as exc:
            msg = str(exc)
            if _is_trigger_error(msg):
                raise EntityValidationError(msg) from exc
            raise
        return self._load_card(card_id)

    def _load_card(self, card_id: UUID) -> Card:
        card = self._cards.get(card_id)
        if card.card_type is None:
            try:
                card.card_type = self._card_types.get(card.card_type_id)
            except EntityNotFoundError:
                pass
        return card
