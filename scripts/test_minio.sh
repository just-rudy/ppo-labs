#!/usr/bin/env bash
# Тестирование MinIO — загрузка изображения карты и получение ссылки
# Запуск: bash scripts/test_minio.sh  или  make test-minio
#
# Что показывает:
#   1. Список бакетов и объектов до загрузки
#   2. Загрузку изображения через API (POST /cards/{id}/image)
#   3. Что объект появился в MinIO
#   4. URL изображения из ответа API
#   5. Прямую загрузку объекта через mc (без API)
#   6. Список объектов после

set -euo pipefail

API_BASE="${API_BASE_URL:-http://localhost:8000/api/v1}"
MINIO_BUCKET="${MINIO_BUCKET:-cards}"
MASTER_ID="${AUTH_USER_ID:-c0ffee00-0000-4000-8000-0000000000ee}"
# Каждый --rm контейнер получает alias через окружение, без общей конфигурации mc.
MINIO_MC_HOST="${MINIO_MC_HOST:-http://minioadmin:minioadmin@cmb-minio:9000}"

# Сеть docker-compose — mc запускается в той же сети
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
NETWORK="${DOCKER_NETWORK:-${PROJECT_NAME}_default}"

mc() {
    docker run --rm --network "$NETWORK" \
        -e "MC_HOST_local=$MINIO_MC_HOST" minio/mc:latest "$@"
}

echo "=== Диагностика загрузки изображений в MinIO ==="

# ─── 1. Состояние до загрузки ─────────────────────────────────────────────────
echo ""
echo "-- Бакеты в MinIO"
mc ls local

echo ""
echo "-- Объекты в бакете $MINIO_BUCKET (до загрузки)"
mc ls --recursive "local/$MINIO_BUCKET" 2>/dev/null || echo "  (пусто)"

# ─── 2. Загрузка через API ────────────────────────────────────────────────────
echo ""
echo "-- Получаем карту из API"

CARD_ID=$(curl -fsS "$API_BASE/cards" \
    | python3 -c "
import sys, json
cards = json.load(sys.stdin)
print(cards[0]['id'] if cards else '')
" 2>/dev/null || echo "")

if [[ -z "$CARD_ID" ]]; then
    echo "Нет карт. Запустите: make db-seed"
    exit 1
fi

echo "  Карта:  $CARD_ID"
echo "  Мастер: $MASTER_ID"

# Минимальный валидный PNG 1×1 (не требует внешнего файла)
DEMO_PNG_B64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

# Если есть реальный файл — берём его
ASSET="$PROJECT_DIR/assets/cards/default-image.png"
if [[ -f "$ASSET" ]]; then
    IMG_B64=$(base64 -w0 "$ASSET")
    echo "  Файл: $ASSET"
else
    IMG_B64="$DEMO_PNG_B64"
    echo "  Файл: встроенный PNG 1×1 (assets/cards/default-image.png не найден)"
fi

echo ""
echo "-- POST $API_BASE/cards/$CARD_ID/image"
PAYLOAD_FILE=$(mktemp)
trap 'rm -f "$PAYLOAD_FILE"' EXIT
# Base64 реальной картинки может превышать лимит размера аргумента процесса.
printf '%s' "$IMG_B64" | python3 -c '
import json, sys
json.dump({"filename": "test-debug.png", "content_base64": sys.stdin.read(),
           "content_type": "image/png"}, sys.stdout)
' > "$PAYLOAD_FILE"
RESPONSE=$(curl -fsS -X POST "$API_BASE/cards/$CARD_ID/image" \
    -H "Content-Type: application/json" \
    -H "X-User-Id: $MASTER_ID" \
    --data-binary "@$PAYLOAD_FILE")

echo "$RESPONSE" | python3 -m json.tool 2>/dev/null | grep -E '"id"|"file"|"url"|"title"' || echo "$RESPONSE"

IMG_FILE=$(echo "$RESPONSE" \
    | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('image',{}).get('file','') or '')" \
    2>/dev/null || echo "")
IMG_URL=$(echo "$RESPONSE" \
    | python3 -c "import sys,json; r=json.load(sys.stdin); print(r.get('image',{}).get('url','') or '')" \
    2>/dev/null || echo "")

# ─── 3. Объекты после загрузки ────────────────────────────────────────────────
echo ""
echo "-- Объекты в бакете $MINIO_BUCKET (после загрузки)"
mc ls --recursive "local/$MINIO_BUCKET" 2>/dev/null || echo "  (пусто)"

if [[ -n "$IMG_FILE" && "$IMG_FILE" != "null" ]]; then
    echo ""
    echo "-- Метаданные объекта: $IMG_FILE"
    mc stat "local/$MINIO_BUCKET/$IMG_FILE" 2>/dev/null \
        | grep -E "Name|Date|Size|Type" || true

    echo ""
    echo "-- URL для скачивания (из ответа API)"
    echo "   $IMG_URL"
fi

# ─── 4. Прямая загрузка через mc ─────────────────────────────────────────────
echo ""
echo "-- Прямая загрузка объекта через mc (без API)"
OBJ="demo/test-direct.txt"
echo "Cool Magic Battles — прямая загрузка в MinIO" \
    | docker run --rm -i --network "$NETWORK" \
        -e "MC_HOST_local=$MINIO_MC_HOST" minio/mc:latest pipe "local/$MINIO_BUCKET/$OBJ"
echo "  Загружен: $MINIO_BUCKET/$OBJ"

echo ""
echo "-- Читаем загруженный объект"
mc cat "local/$MINIO_BUCKET/$OBJ"

echo ""
echo "-- Удаляем тестовый объект"
mc rm "local/$MINIO_BUCKET/$OBJ"
echo "  Удалён: $MINIO_BUCKET/$OBJ"

# ─── 5. Итог ──────────────────────────────────────────────────────────────────
echo ""
echo "-- Итоговый список объектов в бакете"
mc ls --recursive "local/$MINIO_BUCKET" 2>/dev/null || echo "  (пусто)"

echo ""
echo "Веб-консоль по умолчанию: http://localhost:9001"
echo ""
echo "=== Готово ==="
