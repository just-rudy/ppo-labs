#!/usr/bin/env bash
# Тестирование триггера card_validate_trigger
# Запуск: bash scripts/test_trigger.sh  или  make test-trigger

PG="docker exec -i cmb-postgres psql -U cmb -d cool_magic_battles"

run() {
    local label="$1"
    local sql="$2"
    echo ""
    echo "-- $label"
    echo "$sql"
    result=$($PG -c "$sql" 2>&1)
    echo "$result"
}

echo "=== Триггер валидации карты ==="

run "Нарушение: cost = 0" \
"INSERT INTO cards (id, title, creature, power, echo, cost, cool_points, card_type_id, image_id)
SELECT gen_random_uuid(), 'Bad Cost', 'elf', 1, 1, 0, 0,
  (SELECT id FROM card_types LIMIT 1), (SELECT id FROM images LIMIT 1);"

run "Нарушение: cost = 8" \
"INSERT INTO cards (id, title, creature, power, echo, cost, cool_points, card_type_id, image_id)
SELECT gen_random_uuid(), 'Bad Cost High', 'elf', 1, 1, 8, 0,
  (SELECT id FROM card_types LIMIT 1), (SELECT id FROM images LIMIT 1);"

run "Нарушение: power = 0" \
"INSERT INTO cards (id, title, creature, power, echo, cost, cool_points, card_type_id, image_id)
SELECT gen_random_uuid(), 'Bad Power', 'elf', 0, 1, 3, 0,
  (SELECT id FROM card_types LIMIT 1), (SELECT id FROM images LIMIT 1);"

run "Нарушение: cool_points = 6" \
"INSERT INTO cards (id, title, creature, power, echo, cost, cool_points, card_type_id, image_id)
SELECT gen_random_uuid(), 'Bad Points', 'elf', 1, 1, 3, 6,
  (SELECT id FROM card_types LIMIT 1), (SELECT id FROM images LIMIT 1);"

run "Нарушение: cool_points = -2" \
"INSERT INTO cards (id, title, creature, power, echo, cost, cool_points, card_type_id, image_id)
SELECT gen_random_uuid(), 'Bad Points Low', 'elf', 1, 1, 3, -2,
  (SELECT id FROM card_types LIMIT 1), (SELECT id FROM images LIMIT 1);"

run "Нарушение: buff_* с пустым creature" \
"INSERT INTO cards (id, title, creature, power, echo, cost, cool_points, card_type_id, image_id)
SELECT gen_random_uuid(), 'Bad Buff', '', 1, 1, 3, 0,
  (SELECT id FROM card_types WHERE action LIKE 'buff_%' LIMIT 1),
  (SELECT id FROM images LIMIT 1);"

run "Корректная карта (cost=4, power=2, cool_points=1)" \
"INSERT INTO cards (id, title, creature, power, echo, cost, cool_points, card_type_id, image_id)
SELECT gen_random_uuid(), 'Valid Card Demo', 'dwarf', 2, 1, 4, 1,
  (SELECT id FROM card_types LIMIT 1), (SELECT id FROM images LIMIT 1);"

run "Нарушение при UPDATE: cost = 0 на существующей карте" \
"UPDATE cards SET cost = 0 WHERE title = 'Valid Card Demo';"

# Чистим за собой
$PG -c "DELETE FROM cards WHERE title = 'Valid Card Demo';" > /dev/null 2>&1

echo ""
echo "=== Готово ==="
