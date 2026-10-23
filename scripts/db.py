#!/usr/bin/env python3
"""Управление БД: миграции Alembic и тестовые данные."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _alembic_executable() -> str:
    """CLI alembic из venv; не использовать python -m alembic — конфликт с ./alembic/."""  # noqa: E501
    venv_alembic = Path(sys.executable).resolve().parent / "alembic"
    if venv_alembic.is_file():
        return str(venv_alembic)
    found = shutil.which("alembic")
    if found:
        return found
    raise RuntimeError("alembic not found. Install: pip install alembic")


def _run_alembic(args: list[str]) -> int:
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    result = subprocess.run(
        [_alembic_executable(), *args],
        cwd=ROOT,
        env=env,
        check=False,
    )
    return result.returncode


def cmd_upgrade(_: argparse.Namespace) -> int:
    return _run_alembic(["upgrade", "head"])


def cmd_downgrade(args: argparse.Namespace) -> int:
    target = args.revision or "-1"
    return _run_alembic(["downgrade", target])


def cmd_revision(args: argparse.Namespace) -> int:
    cmd = ["revision", "-m", args.message]
    if args.autogenerate:
        cmd.append("--autogenerate")
    return _run_alembic(cmd)


def cmd_current(_: argparse.Namespace) -> int:
    return _run_alembic(["current"])


def cmd_stamp(_: argparse.Namespace) -> int:
    return _run_alembic(["stamp", "head"])


def _make_session_factory() -> sessionmaker[Session]:
    sys.path.insert(0, str(SRC))

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    from config.config import load_config

    config = load_config()
    engine = create_engine(config.database.url, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


MEGA_USER_ID = "c0ffee00-0000-4000-8000-0000000000ee"
MEGA_USERNAME = "mega_user"
MEGA_PASSWORD = "cool_password"


def cmd_seed(args: argparse.Namespace) -> int:
    from uuid import UUID, uuid4

    from sqlalchemy import select

    from application.services.card_factory import generate_cards, list_card_types
    from domain.enums import UserRole
    from infrastructure.db.models import CardModel, CardTypeModel, ImageModel, UserModel
    from infrastructure.shared.passwords import hash_password

    SessionLocal = _make_session_factory()
    mega_password_hash = hash_password(MEGA_PASSWORD)

    # seed_users: (username, user_id, role, password_hash | None)
    seed_users = [
        ("guest_user", uuid4(), UserRole.GUEST, None),
        ("gandalf", uuid4(), UserRole.AUTHENTICATED, None),
        ("saruman", uuid4(), UserRole.PLAYER, None),
        ("radagast", uuid4(), UserRole.MODERATOR, None),
        ("elrond", uuid4(), UserRole.MASTER, None),
        (
            MEGA_USERNAME,
            UUID(MEGA_USER_ID),
            UserRole.MASTER,
            mega_password_hash,
        ),
    ]

    with SessionLocal() as session:
        for username, user_id, role, password_hash in seed_users:
            exists = session.scalar(
                select(UserModel).where(UserModel.username == username)
            )
            if exists:
                if username == MEGA_USERNAME:
                    exists.role = UserRole.MASTER.value
                    exists.password_hash = mega_password_hash
                    print(
                        f"  update {username}  id={exists.id} "
                        f"role={UserRole.MASTER.value} (password reset)"
                    )
                else:
                    print(f"  skip  {username} (already exists)")
                continue
            session.add(
                UserModel(
                    id=user_id,
                    username=username,
                    role=role.value,
                    password_hash=password_hash,
                )
            )
            print(f"  add   {username}  id={user_id} role={role.value}")

        session.commit()

    with SessionLocal() as session:
        existing_card_type_ids = set(session.scalars(select(CardTypeModel.id)))
        for card_type in list_card_types():
            if card_type.id in existing_card_type_ids:
                continue
            session.add(
                CardTypeModel(
                    id=card_type.id,
                    action=card_type.action.value,
                    usage_pattern=card_type.usage_pattern.value,
                    if_permanent=card_type.if_permanent,
                    color=card_type.color,
                )
            )

        session.commit()

    with SessionLocal() as session:
        existing_image_ids = set(session.scalars(select(ImageModel.id)))
        existing_titles = set(session.scalars(select(CardModel.title)))
        current_count = len(existing_titles)
        print(f"Current cards in db: {current_count}")
        target_count = args.cards
        # target_count = 10
        if current_count >= target_count:
            print(f"  skip  card seed (already have {current_count} cards)")
        else:
            # Генерируем достаточно карт, чтобы набрать нужное количество новых
            all_cards = generate_cards(target_count)
            new_cards = [c for c in all_cards if c.title not in existing_titles]
            to_add = target_count - current_count
            new_cards = new_cards[:to_add]
            for card in new_cards:
                if card.image is not None and card.image.id not in existing_image_ids:
                    session.add(
                        ImageModel(
                            id=card.image.id,
                            title=card.image.title,
                            file=card.image.file,
                        )
                    )
                    existing_image_ids.add(card.image.id)
                session.add(
                    CardModel(
                        id=card.id,
                        title=card.title,
                        creature=card.creature,
                        card_type_id=card.card_type_id,
                        image_id=card.image_id,
                        power=card.power,
                        echo=card.echo,
                        cost=card.cost,
                        cool_points=card.cool_points,
                    )
                )
            session.commit()
            print(f"  add   {len(new_cards)} cards")

    print("Seed complete.")
    return 0


def cmd_fix_card_images(args: argparse.Namespace) -> int:
    """Обновляет image_id у карт, у которых стоит дефолтное изображение,
    и создаёт соответствующие записи в таблице images."""
    from uuid import UUID

    from sqlalchemy import select

    from application.services.card_factory import _build_image
    from infrastructure.db.models import CardModel, ImageModel

    DEFAULT_IMAGE_ID = UUID("8156540c-f8aa-5f2a-aef6-3f2cca36bf45")

    SessionLocal = _make_session_factory()

    with SessionLocal() as session:
        cards = (
            session.query(CardModel)
            .filter(CardModel.image_id == DEFAULT_IMAGE_ID)
            .all()
        )

        if not cards:
            print("No cards with default image found — nothing to fix.")
            return 0

        print(f"Found {len(cards)} cards with default image, fixing...")

        existing_image_ids = set(session.scalars(select(ImageModel.id)))
        fixed = 0

        for card in cards:
            image = _build_image(card.title)
            if image.id not in existing_image_ids:
                session.add(
                    ImageModel(
                        id=image.id,
                        title=image.title,
                        file=image.file,
                    )
                )
                existing_image_ids.add(image.id)
            card.image_id = image.id
            fixed += 1

        session.commit()
        print(f"  fixed {fixed} cards")

    print("Done.")
    return 0


def cmd_truncate(args: argparse.Namespace) -> int:
    from sqlalchemy import MetaData, text

    SessionLocal = _make_session_factory()
    metadata = MetaData()

    with SessionLocal() as session:
        metadata.reflect(bind=session.get_bind())

        if args.table not in metadata.tables:
            available_tables = ", ".join(sorted(metadata.tables))
            raise ValueError(
                f"unknown table '{args.table}'. Available tables: {available_tables}"
            )

        cascade_sql = " CASCADE" if args.cascade else ""
        session.execute(text(f'TRUNCATE TABLE "{args.table}"{cascade_sql}'))
        session.commit()

    print(f"Table '{args.table}' truncated.")
    return 0


def cmd_truncate_all(args: argparse.Namespace) -> int:
    from sqlalchemy import MetaData, text

    SessionLocal = _make_session_factory()
    metadata = MetaData()

    with SessionLocal() as session:
        metadata.reflect(bind=session.get_bind())

        table_names = sorted(
            table_name
            for table_name in metadata.tables
            if args.include_alembic or table_name != "alembic_version"
        )
        if not table_names:
            print("No tables to truncate.")
            return 0

        joined_tables = ", ".join(f'"{table_name}"' for table_name in table_names)
        session.execute(text(f"TRUNCATE TABLE {joined_tables} CASCADE"))
        session.commit()

    print(f"Truncated tables: {', '.join(table_names)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Database management")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("upgrade", help="Apply all migrations (alembic upgrade head)")
    sub.add_parser("current", help="Show current revision")
    p_seed = sub.add_parser(
        "seed",
        help="Insert demo users (gandalf, saruman, radagast) and default cards",
    )
    p_seed.add_argument(
        "--cards",
        type=int,
        default=100,
        help="Number of card records to populate in the database",
    )
    sub.add_parser(
        "fix-card-images",
        help="Fix cards with default image by creating per-card image records",
    )
    p_truncate = sub.add_parser("truncate", help="Delete all rows from a table")
    p_truncate.add_argument("table", help="Table name to truncate")
    p_truncate.add_argument(
        "--cascade",
        action="store_true",
        help="Also truncate dependent tables via CASCADE",
    )
    p_truncate_all = sub.add_parser(
        "truncate-all",
        help="Delete all rows from all tables in the current database",
    )
    p_truncate_all.add_argument(
        "--include-alembic",
        action="store_true",
        help="Also truncate alembic_version",
    )

    p_down = sub.add_parser("downgrade", help="Rollback migrations")
    p_down.add_argument(
        "revision",
        nargs="?",
        help="Target revision (default: -1 = one step back)",
    )

    p_rev = sub.add_parser("revision", help="Create new migration")
    p_rev.add_argument("message", help="Migration message")
    p_rev.add_argument(
        "--autogenerate",
        action="store_true",
        help="Autogenerate from SQLAlchemy models",
    )
    sub.add_parser("stamp", help="Mark DB schema as up-to-date (alembic stamp head)")

    args = parser.parse_args()
    handlers = {
        "upgrade": cmd_upgrade,
        "downgrade": cmd_downgrade,
        "revision": cmd_revision,
        "current": cmd_current,
        "stamp": cmd_stamp,
        "seed": cmd_seed,
        "fix-card-images": cmd_fix_card_images,
        "truncate": cmd_truncate,
        "truncate-all": cmd_truncate_all,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
