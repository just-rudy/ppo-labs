"""card validation trigger and purchase stored procedure

Revision ID: 011_card_trigger_buy_procedure
Revises: 010_sync_card_type_colors
Create Date: 2026-06-04

Триггер card_validate_trigger:
  - cost:        от 1 до 7 включительно
  - power:       положительная; для buff_* не более 2
  - cool_points: от -1 до 5 включительно
  - card_type_id: NOT NULL
  - creature:    для buff_* не может быть пустым

Хранимая процедура purchase_card(player_id, card_id):
  - проверяет наличие игрока и карты
  - проверяет достаточность эхо
  - атомарно списывает эхо
"""

from collections.abc import Sequence

from alembic import op

revision: str = "011_card_trigger_buy_procedure"
down_revision: str | None = "010_sync_card_type_colors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ──────────────────────────────────────────────────────────────────────────────
# SQL: триггер
# ──────────────────────────────────────────────────────────────────────────────

_TRIGGER_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION card_validate_trigger()
RETURNS trigger AS $$
DECLARE
    action_name TEXT;
BEGIN
    -- 1. Тип карты обязателен
    IF NEW.card_type_id IS NULL THEN
        RAISE EXCEPTION 'Card must have a card type';
    END IF;

    -- 2. Стоимость: от 1 до 7
    IF NEW.cost <= 0 OR NEW.cost > 7 THEN
        RAISE EXCEPTION
            'Card cost must be between 1 and 7, got %', NEW.cost;
    END IF;

    -- 3. Сила: положительная
    IF NEW.power <= 0 THEN
        RAISE EXCEPTION
            'Card power must be positive, got %', NEW.power;
    END IF;

    -- Получаем тип действия карты для проверок buff_*
    SELECT action INTO action_name
    FROM card_types
    WHERE id = NEW.card_type_id;

    IF action_name LIKE 'buff_%' THEN
        -- 3b. Для buff_* сила не более 2
        IF NEW.power > 2 THEN
            RAISE EXCEPTION
                'Power for buff_* card must not exceed 2, got %', NEW.power;
        END IF;
        -- 3c. Для buff_* поле creature обязательно (локация)
        IF NEW.creature IS NULL OR trim(NEW.creature) = '' THEN
            RAISE EXCEPTION
                'buff_* card must have a location in the creature field';
        END IF;
    END IF;

    -- 4. Очки крутости: от -1 до 5
    IF NEW.cool_points < -1 OR NEW.cool_points > 5 THEN
        RAISE EXCEPTION
            'cool_points must be between -1 and 5, got %', NEW.cool_points;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS trg_card_validate ON cards;
CREATE TRIGGER trg_card_validate
    BEFORE INSERT OR UPDATE ON cards
    FOR EACH ROW EXECUTE FUNCTION card_validate_trigger();
"""

_DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS trg_card_validate ON cards;
DROP FUNCTION IF EXISTS card_validate_trigger();
"""

# ──────────────────────────────────────────────────────────────────────────────
# SQL: хранимая процедура покупки
# ──────────────────────────────────────────────────────────────────────────────

_PURCHASE_PROCEDURE_SQL = """
CREATE OR REPLACE FUNCTION purchase_card(
    p_player_id UUID,
    p_card_id   UUID
) RETURNS VOID AS $$
DECLARE
    v_cur_echo  INTEGER;
    v_card_cost INTEGER;
BEGIN
    -- Проверяем игрока
    SELECT cur_echo INTO v_cur_echo
    FROM players
    WHERE id = p_player_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Player % not found', p_player_id;
    END IF;

    -- Проверяем карту
    SELECT cost INTO v_card_cost
    FROM cards
    WHERE id = p_card_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Card % not found', p_card_id;
    END IF;

    -- Проверяем достаточность эхо
    IF v_cur_echo < v_card_cost THEN
        RAISE EXCEPTION
            'Insufficient echo: player has %, card costs %',
            v_cur_echo, v_card_cost;
    END IF;

    -- Атомарно списываем стоимость
    UPDATE players
    SET cur_echo = cur_echo - v_card_cost
    WHERE id = p_player_id;
END;
$$ LANGUAGE plpgsql;
"""

_DROP_PROCEDURE_SQL = "DROP FUNCTION IF EXISTS purchase_card(UUID, UUID);"


# ──────────────────────────────────────────────────────────────────────────────


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(_TRIGGER_FUNCTION_SQL)
    op.execute(_TRIGGER_SQL)
    op.execute(_PURCHASE_PROCEDURE_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(_DROP_TRIGGER_SQL)
    op.execute(_DROP_PROCEDURE_SQL)
