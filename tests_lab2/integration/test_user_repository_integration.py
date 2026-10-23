from uuid import uuid4

import allure
import pytest
from sqlalchemy.orm import Session

from domain.entities import User
from domain.enums import UserRole
from infrastructure.db.exceptions import EntityNotFoundError, PersistenceError
from infrastructure.db.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)

pytestmark = pytest.mark.integration


def test_user_lifecycle_persists_between_connections(engine, db_session):
    repository = SqlAlchemyUserRepository(db_session)
    user = User(id=uuid4(), username="integration_user")
    with allure.step("Save user; verify committed fields in a fresh Session"):
        repository.save(user)
        with Session(engine) as fresh:
            loaded = SqlAlchemyUserRepository(fresh).get(user.id)
            assert loaded.username == user.username
            assert loaded.role == UserRole.AUTHENTICATED
    with allure.step("Update role; verify persisted update"):
        user.role = UserRole.PLAYER
        repository.save(user)
        with Session(engine) as fresh:
            assert SqlAlchemyUserRepository(fresh).get(user.id).role == UserRole.PLAYER
    with allure.step("Duplicate username rejected by PostgreSQL; original unchanged"):
        with pytest.raises(PersistenceError):
            repository.save(User(id=uuid4(), username=user.username))
        with Session(engine) as fresh:
            assert len(SqlAlchemyUserRepository(fresh).list_all()) == 1
    with allure.step("Delete user; missing entity raises expected exception"):
        repository.delete(user.id)
        with Session(engine) as fresh:
            repo = SqlAlchemyUserRepository(fresh)
            assert not repo.exists(user.id)
            with pytest.raises(EntityNotFoundError):
                repo.get(user.id)
