.PHONY: dev build test lint format install setup-db

dev:
	npm run dev

build:
	npm run build

test:
	npm run test

lint:
	cd apps/api && uv run ruff check .
	npm run lint --workspaces

format:
	cd apps/api && uv run ruff format .
	npm run format --workspaces

install:
	npm install
	cd apps/api && uv sync

setup-db:
	# Add supabase local dev setup later
	echo "Supabase dev setup coming soon"
