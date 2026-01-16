.PHONY: up down rebuild restart api-logs test test-cov install-test-deps install-pre-commit

up:
	docker compose up --build -d api
	docker compose logs -f api

down:
	docker compose down

rebuild:
	docker compose down
	docker compose build
	docker compose up -d
	docker compose logs -f api

restart:
	docker compose down
	docker compose up -d
	docker compose logs -f api

api-logs:
	docker compose logs -f api

install-test-deps:
	@if [ ! -d .venv ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv .venv; \
	fi
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e ".[test]"

install-pre-commit: install-test-deps
	.venv/bin/pip install pre-commit
	.venv/bin/pre-commit install

test:
	.venv/bin/pytest tests/ -v

test-cov:
	.venv/bin/pytest tests/ -v --cov=src/api --cov-branch --cov-report=term --cov-report=html

test-watch:
	.venv/bin/pytest tests/ -v --cov=src/api --cov-branch --cov-report=term -x --pdb
