# Tестирование: памятка

## Что именно тестируется

Проект `cool-magic-battles` использует `pytest` для проверки бизнес-логики.
Основные SUT:

- `CardLogic`
- `DeckService`
- `GameLogic`
- `GameStateManager`

В лабораторном наборе 10 unit-тестов:

- 5 классических тестов: реальные объекты, проверка состояния
- 5 лондонских тестов: `GameLogic` как SUT, сотрудники подменяются mock-объектами
- все тесты offline, без сетевых зависимостей

## Основные команды

```bash
make test-unit          # 10 unit-тестов из lab-patterns
make test-repositories  # реальные SQLAlchemy-репозитории, SQLite in-memory
make test-unit-random   # тот же набор в случайном порядке
make test-unit-offline  # pytest --disable-socket
make coverage           # покрытие проекта + HTML в htmlcov/
make allure-report      # запуск тестов + генерация Allure-report
make allure-open        # открыть HTML-отчёт Allure локально
```

## Прямой запуск pytest

```bash
PYTHONPATH=src pytest src/tests/domain/test_lab_patterns.py
PYTHONPATH=src pytest src/tests/integration
PYTHONPATH=src pytest src/tests/domain/test_lab_patterns.py --randomly-seed=$(date +%s)
PYTHONPATH=src pytest src/tests/domain/test_lab_patterns.py --disable-socket -m offline
PYTHONPATH=src pytest src/tests/domain/test_lab_patterns.py \
  --cov=src --cov-config=pyproject.toml --cov-report=term --cov-report=html:htmlcov
```

## Маркеры pytest

Конфигурация в `pytest.ini` / `pyproject.toml`:

- `unit` — изолированные unit-тесты
- `classic` — классическая школа: реальные объекты и итоговое состояние
- `london` — лондонская школа: mocks и проверка взаимодействий
- `offline` — запуск без сетевых сокетов

Примеры:

```bash
PYTHONPATH=src pytest -m classic
PYTHONPATH=src pytest -m london
PYTHONPATH=src pytest -m offline
```

## Что такое fixture

`fixture` в pytest — функция, которая подготавливает контекст и передаёт его в тест.

Пример из проекта:

- `london_context` создаёт новый `GameLogic`
- и отдельные mock-объекты (`game_repository`, `user_repository`, `card_logic`, `deck_service`, `state_manager`, `card_type_repository`)
- это гарантирует изоляцию тестов и отсутствие побочных эффектов

## Builder / ObjectMother

Используются helpers для создания корректных сущностей:

- `CardBuilder` — строит карточки с нужными параметрами
- `PlayerBuilder` — создаёт игрока с `hand`, `draw_pile`, `table`, `health`, `echo` и т.д.
- `ObjectMother` — фабрика типовых объектов: карта, пользователь, игра

## Классический подход

Тесты используют реальные объекты и проверяют конечное состояние.

Основные сценарии:

1. Добор нужного количества карт
2. Лечение около максимального здоровья
3. Атака без цели
4. Передача хода следующему игроку
5. Завершение хода с обработкой атаки, сбросом карт, восстановлением эха, сменой активного игрока

## Лондонский подход

`GameLogic` выступает в роли SUT, а его зависимости заменяются mock-объектами.

Основные сценарии:

1. Создание игры и сохранение сущности
2. Добавление игрока, смена роли и сохранение
3. Ошибка при покупке при недостаточном эхо
4. Атака и создание `pending_attack`
5. Защита не DEF-картой -> исключение

## Проверки покрытия

Команда:

```bash
make coverage
```

Генерирует:

- вывод в терминал по lab-модулям и по всему проекту
- HTML-отчёт в `htmlcov/index.html`

Покрываются:

- `card_logic.py`
- `deck_service.py`
- `game_logic.py`
- `game_state_manager.py`
- а также все production-файлы в `src`

## Allure

```bash
make allure-report
make allure-open
```

Логика:

- очищаются старые результаты
- запускаются 10 unit-тестов
- выгружаются данные в `build/allure-results`
- генерируется HTML-отчёт в `build/allure-report`

## Важные замечания

- pytest запускает один процесс на весь набор
- parallel execution не включён (`pytest-xdist` не используется)
- `make test-unit-offline` запрещает сетевые сокеты через `pytest-socket`
- для интеграционных тестов используется SQLite in-memory, без PostgreSQL/Docker/internet
- `make coverage` не включён в обычный запуск по умолчанию; это отдельная команда

## Короткая шпаргалка для защиты

```bash
make test-unit
make test-repositories
make coverage
make allure-report
```

Если нужно быстро проверить только лабораторный набор:

```bash
PYTHONPATH=src pytest src/tests/domain/test_lab_patterns.py -q
```
