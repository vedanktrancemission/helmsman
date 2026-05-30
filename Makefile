.PHONY: up down logs test dev-api dev-web setup

# One command: build + start db, redis, api, web.
up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api

# Local (no Docker) backend — SQLite + in-memory bus.
setup:
	cd server && pip install -r requirements.txt
	cd web && npm install

dev-api:
	cd server && uvicorn app.main:app --reload --port 8000

dev-web:
	cd web && npm run dev

test:
	cd server && PYTHONPATH=. pytest -q
