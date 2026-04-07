.PHONY: up down test lint migrate ingest backfill fmt check

up:
	docker compose up -d

down:
	docker compose down

test:
	uv run pytest --cov=trace_app --cov-report=term-missing --cov-fail-under=60

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/
	uv run mypy src/

fmt:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

migrate:
	uv run alembic upgrade head

AGENCY ?= FERC

ingest:
	uv run python -m trace_app.connectors.ingest --agency $(AGENCY)

backfill:
	uv run python -m trace_app.connectors.backfill

check: lint test
