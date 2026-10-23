#!/usr/bin/env bash
# Тестирование хранимой процедуры purchase_card
# Запуск: bash scripts/test_procedure.sh  или  make test-procedure

PG="docker exec -i cmb-postgres psql -U cmb -d cool_magic_battles"

run() {
    local label="$1"
    local sql="$2"
    echo ""
    echo "-- $label"
    echo "$sql"
    $PG -c "$sql" 2>&1
}

echo "=== Хранимая процедура purchase_card ==="

# Ищем игрока с ненулевым эхо и карту на рынке
PLAYER_ID=$($PG --no-align --tuples-only \
    -c "SELECT id FROM players WHERE cur_echo > 0 LIMIT 1;" 2>/dev/null | tr -d ' ')
PLAYER_ECHO=$($PG --no-align --tuples-only \
    -c "SELECT cur_echo FROM players WHERE id='$PLAYER_ID';" 2>/dev/null | tr -d ' ')
CARD_ID=$($PG --no-align --tuples-only -c "
SELECT c.id FROM cards c
JOIN deck_cards dc ON dc.card_id = c.id
JOIN decks d ON dc.deck_id = d.id
WHERE d.type = 'market' AND c.cost <= $PLAYER_ECHO
LIMIT 1;" 2>/dev/null | tr -d ' ')
CARD_COST=$($PG --no-align --tuples-only \
    -c "SELECT cost FROM cards WHERE id='$CARD_ID';" 2>/dev/null | tr -d ' ')

if [[ -z "$PLAYER_ID" || -z "$CARD_ID" ]]; then
    echo ""
    echo "Нет данных для теста: нужна запущенная игра с игроками и рынком."
    echo "Запустите игру через API, затем повторите."
    exit 0
fi

echo ""
echo "Игрок: $PLAYER_ID  (cur_echo = $PLAYER_ECHO)"
echo "Карта:  $CARD_ID  (cost = $CARD_COST)"

run "Состояние ДО покупки" \
"SELECT id, cur_echo FROM players WHERE id = '$PLAYER_ID';"

run "Покупка карты (достаточно эхо)" \
"SELECT purchase_card('$PLAYER_ID', '$CARD_ID');"

run "Состояние ПОСЛЕ покупки (эхо уменьшилось на $CARD_COST)" \
"SELECT id, cur_echo FROM players WHERE id = '$PLAYER_ID';"

run "Тест: обнуляем эхо" \
"UPDATE players SET cur_echo = 0 WHERE id = '$PLAYER_ID';"

run "Покупка при нулевом эхо — ошибка" \
"SELECT purchase_card('$PLAYER_ID', '$CARD_ID');"

run "Тест: несуществующий игрок — ошибка" \
"SELECT purchase_card('00000000-0000-0000-0000-000000000000', '$CARD_ID');"

run "Тест: несуществующая карта — ошибка" \
"SELECT purchase_card('$PLAYER_ID', '00000000-0000-0000-0000-000000000000');"

# Восстанавливаем эхо
$PG -c "UPDATE players SET cur_echo = $PLAYER_ECHO WHERE id = '$PLAYER_ID';" > /dev/null 2>&1

echo ""
echo "=== Готово (эхо игрока восстановлено) ==="
