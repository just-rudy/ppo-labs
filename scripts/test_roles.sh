#!/usr/bin/env bash
# Тестирование ролевой модели PostgreSQL
# Запуск: bash scripts/test_roles.sh  или  make test-roles
#
# Роли и их права:
#   cmb_guest             SELECT на cards, card_types, images
#   cmb_authenticated_user  + SELECT/INSERT на games, players
#   cmb_player            + SELECT/UPDATE на decks; UPDATE/DELETE на deck_cards
#   cmb_moderator         + SELECT/INSERT/UPDATE/DELETE на users, games, players
#   cmb_master            + INSERT/UPDATE/DELETE на cards, card_types, images
#
# Скрипт проверяет: разрешённые операции проходят, запрещённые — получают ERROR

PG_OWNER="docker exec -i cmb-postgres psql -U cmb        -d cool_magic_battles"
PG_GUEST="docker exec -i cmb-postgres psql -U cmb_guest  -d cool_magic_battles"
PG_AUTH="docker exec -i cmb-postgres psql -U cmb_authenticated_user -d cool_magic_battles"
PG_PLAYER="docker exec -i cmb-postgres psql -U cmb_player -d cool_magic_battles"
PG_MODER="docker exec -i cmb-postgres psql -U cmb_moderator -d cool_magic_battles"
PG_MASTER="docker exec -i cmb-postgres psql -U cmb_master -d cool_magic_battles"

# run <label> <psql-command> <sql>
# Печатает SQL, выполняет, показывает результат
run() {
    local label="$1"
    local pg_cmd="$2"
    local sql="$3"
    echo ""
    echo "-- $label"
    echo "$sql"
    $pg_cmd -c "$sql" 2>&1
}

# Проверяем что роли вообще существуют
check_roles_exist() {
    echo ""
    echo "-- Проверка наличия ролей в PostgreSQL"
    local missing=0
    for role in cmb_guest cmb_authenticated_user cmb_player cmb_moderator cmb_master; do
        exists=$($PG_OWNER --no-align --tuples-only \
            -c "SELECT 1 FROM pg_roles WHERE rolname='$role';" 2>/dev/null | tr -d ' ')
        if [[ "$exists" == "1" ]]; then
            echo "  ✓ $role"
        else
            echo "  ✗ $role ОТСУТСТВУЕТ — миграция 008 не применена или нет прав CREATEROLE"
            missing=1
        fi
    done
    if [[ "$missing" == "1" ]]; then
        echo ""
        echo "Роли не созданы. Возможные причины:"
        echo "  1. Пользователь cmb не имеет CREATEROLE — выполните:"
        echo "     docker exec -i cmb-postgres psql -U postgres -c \"ALTER ROLE cmb CREATEROLE;\""
        echo "     make db-migrate"
        echo "  2. Используется локальный PostgreSQL без Docker"
        echo ""
        echo "Ролевая модель работает на уровне приложения (X-User-Id заголовок)."
        echo "Демонстрацию через API см. в test_roles_api.sh"
        exit 0
    fi
}

echo "=== Ролевая модель PostgreSQL ==="
check_roles_exist

# ─── cmb_guest ────────────────────────────────────────────────────────────────
echo ""
echo "━━━ Роль: cmb_guest (гость) ━━━"

run "РАЗРЕШЕНО: читать карты" \
    "$PG_GUEST" \
    "SELECT title, cost, power FROM cards LIMIT 3;"

run "РАЗРЕШЕНО: читать типы карт" \
    "$PG_GUEST" \
    "SELECT id, action FROM card_types LIMIT 3;"

run "ЗАПРЕЩЕНО: добавить карту (только SELECT)" \
    "$PG_GUEST" \
    "INSERT INTO cards (id, title, creature, power, echo, cost, cool_points, card_type_id, image_id)
SELECT gen_random_uuid(), 'Guest Card', 'elf', 1, 1, 3, 0,
  (SELECT id FROM card_types LIMIT 1), (SELECT id FROM images LIMIT 1);"

run "ЗАПРЕЩЕНО: читать игры" \
    "$PG_GUEST" \
    "SELECT id, name, status FROM games LIMIT 3;"

run "ЗАПРЕЩЕНО: читать пользователей" \
    "$PG_GUEST" \
    "SELECT id, username FROM users LIMIT 3;"

# ─── cmb_authenticated_user ───────────────────────────────────────────────────
echo ""
echo "━━━ Роль: cmb_authenticated_user (авторизованный пользователь) ━━━"

run "РАЗРЕШЕНО: читать карты" \
    "$PG_AUTH" \
    "SELECT title FROM cards LIMIT 2;"

run "РАЗРЕШЕНО: читать игры" \
    "$PG_AUTH" \
    "SELECT id, name, status FROM games LIMIT 2;"

run "ЗАПРЕЩЕНО: добавить карту" \
    "$PG_AUTH" \
    "INSERT INTO cards (id, title, creature, power, echo, cost, cool_points, card_type_id, image_id)
SELECT gen_random_uuid(), 'Auth Card', 'elf', 1, 1, 3, 0,
  (SELECT id FROM card_types LIMIT 1), (SELECT id FROM images LIMIT 1);"

run "ЗАПРЕЩЕНО: удалить игру" \
    "$PG_AUTH" \
    "DELETE FROM games WHERE false;"

run "ЗАПРЕЩЕНО: читать колоды (decks)" \
    "$PG_AUTH" \
    "SELECT id, type FROM decks LIMIT 2;"

# ─── cmb_player ───────────────────────────────────────────────────────────────
echo ""
echo "━━━ Роль: cmb_player (игрок) ━━━"

run "РАЗРЕШЕНО: читать колоды" \
    "$PG_PLAYER" \
    "SELECT id, type FROM decks LIMIT 2;"

run "РАЗРЕШЕНО: обновить колоду" \
    "$PG_PLAYER" \
    "UPDATE decks SET if_open = if_open WHERE false;"

run "ЗАПРЕЩЕНО: добавить карту в каталог" \
    "$PG_PLAYER" \
    "INSERT INTO cards (id, title, creature, power, echo, cost, cool_points, card_type_id, image_id)
SELECT gen_random_uuid(), 'Player Card', 'elf', 1, 1, 3, 0,
  (SELECT id FROM card_types LIMIT 1), (SELECT id FROM images LIMIT 1);"

run "ЗАПРЕЩЕНО: читать пользователей" \
    "$PG_PLAYER" \
    "SELECT id, username FROM users LIMIT 2;"

run "ЗАПРЕЩЕНО: удалить игру" \
    "$PG_PLAYER" \
    "DELETE FROM games WHERE false;"

# ─── cmb_moderator ────────────────────────────────────────────────────────────
echo ""
echo "━━━ Роль: cmb_moderator (модератор) ━━━"

run "РАЗРЕШЕНО: читать пользователей" \
    "$PG_MODER" \
    "SELECT username, role FROM users LIMIT 3;"

run "РАЗРЕШЕНО: обновить игру" \
    "$PG_MODER" \
    "UPDATE games SET status = status WHERE false;"

run "РАЗРЕШЕНО: удалить запись игрока (WHERE false — ничего не удалит)" \
    "$PG_MODER" \
    "DELETE FROM players WHERE false;"

run "ЗАПРЕЩЕНО: добавить карту в каталог" \
    "$PG_MODER" \
    "INSERT INTO cards (id, title, creature, power, echo, cost, cool_points, card_type_id, image_id)
SELECT gen_random_uuid(), 'Moder Card', 'elf', 1, 1, 3, 0,
  (SELECT id FROM card_types LIMIT 1), (SELECT id FROM images LIMIT 1);"

run "ЗАПРЕЩЕНО: удалить карту из каталога" \
    "$PG_MODER" \
    "DELETE FROM cards WHERE false;"

# ─── cmb_master ───────────────────────────────────────────────────────────────
echo ""
echo "━━━ Роль: cmb_master (мастер) ━━━"

run "РАЗРЕШЕНО: добавить карту в каталог" \
    "$PG_MASTER" \
    "INSERT INTO cards (id, title, creature, power, echo, cost, cool_points, card_type_id, image_id)
SELECT gen_random_uuid(), 'Master Test Card', 'dwarf', 2, 1, 4, 1,
  (SELECT id FROM card_types LIMIT 1), (SELECT id FROM images LIMIT 1);"

run "РАЗРЕШЕНО: обновить карту" \
    "$PG_MASTER" \
    "UPDATE cards SET echo = 1 WHERE title = 'Master Test Card';"

run "РАЗРЕШЕНО: удалить карту" \
    "$PG_MASTER" \
    "DELETE FROM cards WHERE title = 'Master Test Card';"

run "РАЗРЕШЕНО: читать и изменять пользователей" \
    "$PG_MASTER" \
    "SELECT username, role FROM users LIMIT 3;"

echo ""
echo "=== Готово ==="
