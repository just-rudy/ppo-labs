from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.dependencies import (
    get_card_image_service,
    get_db,
    get_redis_cache,
    require_permission,
)
from api.routers.games import build_card_response
from application.dto.requests import (
    CreateCardRequest,
    UpdateCardImageRequest,
    UpdateCardRequest,
)
from application.dto.responses import CardResponse, CardTypeResponse
from application.interfaces.card_repository import CardRepository
from application.interfaces.card_type_repository import CardTypeRepository
from application.services.access_control import Operation, Resource
from application.services.card_catalog_service import CardCatalogService
from application.services.card_image_service import CardImageService
from domain.card_colors import color_for_action
from infrastructure.cache.catalog_cache import (
    get_cached_card_types,
    get_cached_cards,
    set_cached_card_types,
    set_cached_cards,
)
from infrastructure.cache.redis_cache import RedisCache, invalidate_catalog_cache
from infrastructure.db.exceptions import (
    EntityNotFoundError,
    EntityValidationError,
    PersistenceError,
)

router = APIRouter()


def get_card_repository(
    session: Annotated[Session, Depends(get_db)],
) -> CardRepository:
    from api.dependencies import _make_repositories

    _, _, card_repo, _ = _make_repositories(session)
    return card_repo


def get_card_type_repository(
    session: Annotated[Session, Depends(get_db)],
) -> CardTypeRepository:
    from api.dependencies import _make_repositories

    _, _, _, card_type_repo = _make_repositories(session)
    return card_type_repo


def get_card_catalog_service(
    card_repository: Annotated[CardRepository, Depends(get_card_repository)],
    card_type_repository: Annotated[
        CardTypeRepository, Depends(get_card_type_repository)
    ],
) -> CardCatalogService:
    return CardCatalogService(card_repository, card_type_repository)


@router.get("", response_model=list[CardResponse])
def list_cards(
    repository: Annotated[CardRepository, Depends(get_card_repository)],
    image_service: Annotated[CardImageService, Depends(get_card_image_service)],
    cache: Annotated[RedisCache, Depends(get_redis_cache)],
) -> list[CardResponse]:
    cached = get_cached_cards(cache)
    if cached is not None:
        return cached

    responses = [
        build_card_response(card, image_service) for card in repository.list_all()
    ]
    set_cached_cards(cache, responses)
    return responses


@router.get("/types", response_model=list[CardTypeResponse])
def list_card_types(
    repository: Annotated[CardTypeRepository, Depends(get_card_type_repository)],
    cache: Annotated[RedisCache, Depends(get_redis_cache)],
) -> list[CardTypeResponse]:
    cached = get_cached_card_types(cache)
    if cached is not None:
        return cached

    responses = [
        CardTypeResponse(
            id=card_type.id,
            action=card_type.action.value,
            usage_pattern=card_type.usage_pattern.value,
            color=color_for_action(card_type.action),
        )
        for card_type in repository.list_all()
    ]
    set_cached_card_types(cache, responses)
    return responses


@router.get("/rules")
def get_rules() -> dict[str, str]:
    return {
        "title": "Правила игры",
        "url": "https://www.mosigra.ru/download/rules/jepichnie-shvatki-boevih-magov-krutagidon-2025-rules.pdf",
    }


@router.get("/{card_id}", response_model=CardResponse)
def get_card(
    card_id: UUID,
    repository: Annotated[CardRepository, Depends(get_card_repository)],
    image_service: Annotated[CardImageService, Depends(get_card_image_service)],
) -> CardResponse:
    try:
        return build_card_response(repository.get(card_id), image_service)
    except EntityNotFoundError as ex:
        raise HTTPException(status_code=404, detail=str(ex)) from ex


@router.post("", response_model=CardResponse, status_code=201)
def create_card(
    request: CreateCardRequest,
    service: Annotated[CardCatalogService, Depends(get_card_catalog_service)],
    image_service: Annotated[CardImageService, Depends(get_card_image_service)],
    cache: Annotated[RedisCache, Depends(get_redis_cache)],
    _: Annotated[
        object,
        Depends(require_permission(Resource.CARDS, Operation.CREATE)),
    ],
) -> CardResponse:
    try:
        card = service.create_card(
            title=request.title,
            creature=request.creature,
            card_type_id=request.card_type_id,
            power=request.power,
            echo=request.echo,
            cost=request.cost,
            cool_points=request.cool_points,
        )
        invalidate_catalog_cache(cache)
        return build_card_response(card, image_service)
    except EntityValidationError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex
    except EntityNotFoundError as ex:
        raise HTTPException(status_code=404, detail=str(ex)) from ex
    except PersistenceError as ex:
        raise HTTPException(status_code=409, detail=str(ex)) from ex


@router.put("/{card_id}", response_model=CardResponse)
def update_card(
    card_id: UUID,
    request: UpdateCardRequest,
    service: Annotated[CardCatalogService, Depends(get_card_catalog_service)],
    image_service: Annotated[CardImageService, Depends(get_card_image_service)],
    cache: Annotated[RedisCache, Depends(get_redis_cache)],
    _: Annotated[
        object,
        Depends(require_permission(Resource.CARDS, Operation.UPDATE)),
    ],
) -> CardResponse:
    try:
        card = service.update_card(
            card_id,
            title=request.title,
            creature=request.creature,
            card_type_id=request.card_type_id,
            power=request.power,
            echo=request.echo,
            cost=request.cost,
            cool_points=request.cool_points,
        )
        invalidate_catalog_cache(cache)
        return build_card_response(card, image_service)
    except EntityValidationError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex
    except EntityNotFoundError as ex:
        raise HTTPException(status_code=404, detail=str(ex)) from ex
    except PersistenceError as ex:
        raise HTTPException(status_code=409, detail=str(ex)) from ex


@router.post("/{card_id}/image", response_model=CardResponse)
def upload_card_image(
    card_id: UUID,
    request: UpdateCardImageRequest,
    service: Annotated[CardImageService, Depends(get_card_image_service)],
    cache: Annotated[RedisCache, Depends(get_redis_cache)],
    _: Annotated[
        object,
        Depends(require_permission(Resource.IMAGES, Operation.UPDATE)),
    ],
) -> CardResponse:
    try:
        card = service.upload_card_image(
            card_id=card_id,
            title=request.title,
            filename=request.filename,
            content_base64=request.content_base64,
            content_type=request.content_type,
        )
        invalidate_catalog_cache(cache)
        return build_card_response(card, service)
    except EntityNotFoundError as ex:
        raise HTTPException(status_code=404, detail=str(ex)) from ex
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex


@router.delete("/{card_id}", status_code=204)
def delete_card(
    card_id: UUID,
    repository: Annotated[CardRepository, Depends(get_card_repository)],
    cache: Annotated[RedisCache, Depends(get_redis_cache)],
    _: Annotated[
        object,
        Depends(require_permission(Resource.CARDS, Operation.DELETE)),
    ],
) -> None:
    try:
        repository.delete(card_id)
        invalidate_catalog_cache(cache)
    except EntityNotFoundError as ex:
        raise HTTPException(status_code=404, detail=str(ex)) from ex
