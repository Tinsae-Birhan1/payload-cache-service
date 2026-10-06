.PHONY: install lint format typecheck test check migrate run up down demo

install:  ## Create the virtualenv with all dependencies
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy src tests migrations

test:
	uv run pytest --cov=payload_cache --cov-report=term-missing

check: lint typecheck test  ## Everything CI runs

migrate:
	uv run alembic upgrade head

run: migrate  ## Run the API locally on SQLite with auto-reload
	uv run uvicorn payload_cache.main:create_app --factory --reload

up:  ## Run the API and Postgres in Docker
	docker compose up --build -d

down:
	docker compose down

demo:  ## Send the spec's sample payload three times to show cache reuse
	uv run cache-cli -i examples/sample.json -r 3
