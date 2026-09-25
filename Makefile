.PHONY: help db-up db-down db-wait db-migrate db-seed db-reset db-reseed db-truncate db-truncate-all mongo-up mongo-down mongo-seed redis-up redis-down minio-up minio-down minio-logs infra-up infra-down upload-default-image upload-card-images upload-card-images-offline install run-api run-frontend run-all test-storage-switch demo-mongo demo-teacher run-with-mongo test test-unit test-repositories test-unit-random test-unit-offline coverage coverage-open allure-results allure-report allure-open

# docker compose (v2 plugin) или docker-compose (v1)
ifeq ($(shell docker compose version >/dev/null 2>&1 && echo yes),yes)
  DOCKER_COMPOSE := docker compose
else
  DOCKER_COMPOSE := docker-compose
endif

# После usermod -aG docker группа активна не во всех сессиях; sg docker обходит это.
DOCKER_RUN = sg docker -c "$(DOCKER_COMPOSE) $(1)"

help:
	@echo "Targets:"
	@echo "  make install       - pip install dependencies"
	@echo "  make db-up         - start PostgreSQL (Docker)"
	@echo "  make db-down       - stop PostgreSQL"
	@echo "  make db-check      - check local PostgreSQL (no Docker)"
	@echo "  make db-migrate    - apply Alembic migrations"
	@echo "  make db-seed       - insert demo users"
	@echo "  make db-reset      - downgrade + migrate + seed"
	@echo "  make db-reseed    - truncate all tables + seed (faster than reset)"
	@echo "  make db-truncate   - truncate table: make db-truncate TABLE=cards [CASCADE=1]"
	@echo "  make db-truncate-all - truncate all tables in current DB"
	@echo "  make mongo-up      - start MongoDB on :27017"
	@echo "  make mongo-down    - stop MongoDB"
	@echo "  make mongo-seed    - seed users and cards into MongoDB"
	@echo "  make redis-up      - start Redis on :6379 (кэш каталога карт)"
	@echo "  make redis-down    - stop Redis"
	@echo "  make minio-up      - start MinIO on :9000 and console on :9001"
	@echo "  make minio-down    - stop MinIO"
	@echo "  make minio-logs    - tail MinIO logs"
	@echo "  make infra-up      - start PostgreSQL + Redis + MinIO + Mongo"
	@echo "  make infra-down    - stop all Docker infrastructure"
	@echo "  make upload-card-images DIR=assets/cards - upload images to cards by file name"
	@echo "  make run-api       - FastAPI on :8000"
	@echo "  make run-frontend  - Vite dev server on :5173"
	@echo "  make run-all       - run both API and frontend in parallel"
	@echo "  make test-storage-switch - test PostgreSQL and MongoDB switching"
	@echo "  make demo-mongo    - demo MongoDB functionality"
	@echo "  make demo-teacher  - full demo for teacher"
	@echo "  make demo-postgres - demo PostgreSQL: таблицы, триггер, процедура"
	@echo "  make demo-redis    - demo Redis: кэш каталога, hit/miss, инвалидация"
	@echo "  make demo-minio    - demo MinIO: бакет, загрузка, presigned URL"
	@echo "  make demo-all      - запустить все три демо последовательно"
	@echo "  make run-with-mongo - run API with MongoDB only (no PostgreSQL)"
	@echo "  make test          - run all pytest tests"
	@echo "  make test-unit     - run isolated unit tests"
	@echo "  make test-repositories - test real SQLAlchemy repositories with in-memory SQLite"
	@echo "  make test-unit-random - run unit tests in random order"
	@echo "  make test-unit-offline - run mock/offline-safe tests with sockets disabled"
	@echo "  make coverage      - lab and whole-project coverage in terminal + HTML"
	@echo "  make coverage-open - generate coverage HTML and open it in browser"
	@echo "  make allure-report - generate Allure results and report"
	@echo "  make allure-open   - open generated Allure report in a local server"

install:
	pip install -r requirements.txt

test:
	PYTHONPATH=src pytest

test-unit:
	PYTHONPATH=src pytest src/tests/domain/test_lab_patterns.py

test-repositories:
	PYTHONPATH=src pytest src/tests/integration

test-unit-random:
	PYTHONPATH=src pytest src/tests/domain/test_lab_patterns.py --randomly-seed=$$(date +%s)

test-unit-offline:
	PYTHONPATH=src pytest src/tests/domain/test_lab_patterns.py --disable-socket -m offline

coverage:
	PYTHONPATH=src pytest src/tests/domain/test_lab_patterns.py \
		--cov=src --cov-config=pyproject.toml --cov-report=term --cov-report=html:htmlcov
	@echo "\nCoverage of the four lab modules:"
	coverage report --include='*/application/services/card_logic.py,*/application/services/deck_service.py,*/application/services/game_logic.py,*/application/services/game_state_manager.py'
	@echo "\nCoverage of all production Python code:"
	coverage report

coverage-open: coverage
	@python3 -c "import os, webbrowser; p = os.path.abspath('htmlcov/index.html'); print(f'Opening coverage report: {p}'); webbrowser.open('file://' + p)"

allure-results:
	PYTHONPATH=src pytest src/tests/domain/test_lab_patterns.py \
		--alluredir=build/allure-results --clean-alluredir

allure-report: allure-results
	@if command -v allure >/dev/null 2>&1; then \
		allure generate build/allure-results -o build/allure-report --clean; \
	else \
		echo "Allure results are ready in build/allure-results."; \
		echo "Install Allure CLI to generate HTML report: allure generate build/allure-results -o build/allure-report --clean"; \
	fi

allure-open:
	allure open build/allure-report

db-up:
	$(call DOCKER_RUN,up -d db)

redis-up:
	$(call DOCKER_RUN,up -d redis)

redis-down:
	$(call DOCKER_RUN,stop redis)

minio-up:
	$(call DOCKER_RUN,up -d minio)

mongo-up:
	$(call DOCKER_RUN,up -d mongo)

mongo-down:
	$(call DOCKER_RUN,stop mongo)

mongo-seed:
	STORAGE_BACKEND=mongo PYTHONPATH=src .venv/bin/python scripts/mongo_seed.py

infra-up:
	$(call DOCKER_RUN,up -d db redis minio mongo)

db-down:
	$(call DOCKER_RUN,down)

minio-down:
	$(call DOCKER_RUN,stop minio)

infra-down:
	$(call DOCKER_RUN,down)

minio-logs:
	$(call DOCKER_RUN,logs -f minio)

upload-default-image:
	@test -f assets/cards/default-image.png || (echo "File not found: assets/cards/default-image.png" && exit 1)
	PYTHONPATH=src python3 scripts/upload_default_image.py

upload-card-images:
	@test -n "$(DIR)" || (echo "Usage: make upload-card-images DIR=<folder> [API_BASE_URL=http://localhost:8000/api/v1] [AUTH_USER_ID=...]" && exit 1)
	API_BASE_URL=$(or $(API_BASE_URL),http://localhost:8000/api/v1) \
	AUTH_USER_ID=$(or $(AUTH_USER_ID),c0ffee00-0000-4000-8000-0000000000ee) \
		bash scripts/upload_card_images.sh "$(DIR)"

db-wait:
	@echo "Waiting for PostgreSQL..."
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do \
		sg docker -c "$(DOCKER_COMPOSE) exec -T db pg_isready -U cmb -d cool_magic_battles" >/dev/null 2>&1 && exit 0; \
		sleep 1; \
	done; \
	echo "PostgreSQL did not become ready in time"; exit 1

db-check:
	@psql -d cool_magic_battles -c "SELECT current_database(), current_user;" || \
		(echo "Local DB not ready. Create with: psql -d postgres -c \"CREATE DATABASE cool_magic_battles OWNER $$USER;\"" && exit 1)

db-migrate:
	PYTHONPATH=src python3 scripts/db.py upgrade

db-seed:
	PYTHONPATH=src python3 scripts/db.py seed

db-reset:
	PYTHONPATH=src python3 scripts/db.py downgrade
	PYTHONPATH=src python3 scripts/db.py upgrade
	$(MAKE) db-seed

db-reseed:
	$(MAKE) db-migrate
	PYTHONPATH=src .venv/bin/python scripts/db.py truncate-all
	PYTHONPATH=src .venv/bin/python scripts/db.py seed

db-fix-card-images:
	PYTHONPATH=src python3 scripts/db.py fix-card-images


db-truncate:
	@test -n "$(TABLE)" || (echo "Usage: make db-truncate TABLE=<table> [CASCADE=1]" && exit 1)
	PYTHONPATH=src python3 scripts/db.py truncate "$(TABLE)" $(if $(CASCADE),--cascade)

db-truncate-all:
	PYTHONPATH=src python3 scripts/db.py truncate-all

# Если таблицы уже созданы вручную (create_all), но нет alembic_version:
db-stamp:
	PYTHONPATH=src python3 scripts/db.py stamp

run-api:
	PYTHONPATH=src uvicorn api.app:app --reload --host 0.0.0.0 --port 8000

run-frontend:
	cd frontend && npm run dev

run-all:
	@echo "Starting API and Frontend in parallel..."
	@echo "API will be on http://localhost:8000"
	@echo "Frontend will be on http://localhost:5173"
	@echo "Press Ctrl+C to stop both"
	@trap 'kill 0' EXIT; \
		PYTHONPATH=src uvicorn api.app:app --reload --host 0.0.0.0 --port 8000 & \
		cd frontend && npm run dev

run-with-mongo:
	@echo "Running with MongoDB only (no PostgreSQL)..."
	bash run_with_mongo.sh

demo-postgres:
	bash scripts/demo_postgres.sh

demo-redis:
	bash scripts/demo_redis.sh

demo-minio:
	bash scripts/demo_minio.sh

demo-all: demo-postgres demo-redis demo-minio

test-trigger:
	bash scripts/test_trigger.sh

test-procedure:
	bash scripts/test_procedure.sh

test-roles:
	bash scripts/test_roles.sh

test-minio:
	bash scripts/test_minio.sh
