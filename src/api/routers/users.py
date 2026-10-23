from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.dependencies import (
    CurrentActor,
    get_current_actor,
    get_db,
    require_permission,
)
from application.controllers.user_controller import UserController
from application.dto.responses import UserProfileResponse, UserResponse
from application.services.access_control import Operation, Resource
from domain.enums import UserRole
from infrastructure.db.exceptions import EntityNotFoundError

router = APIRouter()


class RegisterUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=6, max_length=128)
    password_confirm: str = Field(min_length=6, max_length=128)


class LoginUserRequest(BaseModel):
    username: str
    password: str | None = None


class UpdateUserRoleRequest(BaseModel):
    role: UserRole


def get_user_controller(
    session: Annotated[Session, Depends(get_db)],
) -> UserController:
    from api.dependencies import _make_repositories

    _, user_repo, _, _ = _make_repositories(session)
    return UserController(user_repo)


@router.post("/register", response_model=UserResponse)
def register_user(
    request: RegisterUserRequest,
    controller: Annotated[UserController, Depends(get_user_controller)],
) -> UserResponse:
    if request.password != request.password_confirm:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    try:
        user = controller.register_user(request.username, request.password)
    except ValueError as ex:
        message = str(ex)
        status = 409 if "already taken" in message else 400
        raise HTTPException(status_code=status, detail=message) from ex

    return UserResponse(id=user.id, username=user.username, role=user.role.value)


@router.post("/login", response_model=UserResponse)
def login_user(
    request: LoginUserRequest,
    controller: Annotated[UserController, Depends(get_user_controller)],
) -> UserResponse:
    try:
        user = controller.login_user(request.username, request.password)
    except ValueError as ex:
        message = str(ex)
        if "not found" in message:
            status = 404
        elif "invalid password" in message or "password is required" in message:
            status = 401
        else:
            status = 400
        raise HTTPException(status_code=status, detail=message) from ex

    return UserResponse(id=user.id, username=user.username, role=user.role.value)


@router.get("/me", response_model=UserProfileResponse)
def get_current_user_profile(
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    controller: Annotated[UserController, Depends(get_user_controller)],
) -> UserProfileResponse:
    if actor.user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    profile = controller.show_user(actor.user.id)
    return UserProfileResponse(
        id=UUID(str(profile["id"])),
        username=str(profile["username"]),
        role=str(profile["role"]),
        has_password=bool(profile["has_password"]),
    )


@router.get("", response_model=list[UserResponse])
def list_users(
    controller: Annotated[UserController, Depends(get_user_controller)],
    _: Annotated[
        object,
        Depends(require_permission(Resource.USERS, Operation.READ)),
    ],
) -> list[UserResponse]:
    return [
        UserResponse(
            id=UUID(str(user["id"])),
            username=str(user["username"]),
            role=str(user["role"]),
        )
        for user in controller.list_users()
    ]


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: UUID,
    controller: Annotated[UserController, Depends(get_user_controller)],
    _: Annotated[
        object,
        Depends(require_permission(Resource.USERS, Operation.READ)),
    ],
) -> UserResponse:
    try:
        user = controller.show_user(user_id)
    except EntityNotFoundError as ex:
        raise HTTPException(status_code=404, detail="User not found") from ex
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex

    return UserResponse(
        id=UUID(str(user["id"])),
        username=str(user["username"]),
        role=str(user["role"]),
    )


@router.patch("/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: UUID,
    request: UpdateUserRoleRequest,
    controller: Annotated[UserController, Depends(get_user_controller)],
    _: Annotated[
        object,
        Depends(require_permission(Resource.USERS, Operation.UPDATE)),
    ],
) -> UserResponse:
    try:
        user = controller.update_user_role(user_id, request.role)
    except EntityNotFoundError as ex:
        raise HTTPException(status_code=404, detail="User not found") from ex
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex

    return UserResponse(id=user.id, username=user.username, role=user.role.value)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: UUID,
    controller: Annotated[UserController, Depends(get_user_controller)],
    _: Annotated[
        object,
        Depends(require_permission(Resource.USERS, Operation.DELETE)),
    ],
) -> None:
    try:
        controller.delete_user(user_id)
    except EntityNotFoundError as ex:
        raise HTTPException(status_code=404, detail="User not found") from ex
