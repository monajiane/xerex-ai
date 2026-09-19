# Xerex AI — developer entry points.
# Everything here is English: identifiers, targets and log output (PROMPT.md 10).

SHELL := /bin/bash
BACKEND := backend
FRONTEND := frontend
VENV ?= $(HOME)/.local/state/xerex-dev/venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# --- environment ------------------------------------------------------------
.PHONY: venv
venv: ## Create the Python virtualenv used by local development
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel

.PHONY: install
install: venv ## Install backend and frontend dependencies
	$(PIP) install -e "$(BACKEND)[dev]"
	cd $(FRONTEND) && npm install

.PHONY: env
env: ## Create a local .env with generated secrets (never committed)
	@test -f .env || ( \
		SECRET=$$($(PY) -c "import secrets;print(secrets.token_urlsafe(48))"); \
		ENC=$$($(PY) -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"); \
		sed -e "s|^XEREX_SECRET_KEY=.*|XEREX_SECRET_KEY=$$SECRET|" \
		    -e "s|^XEREX_CREDENTIALS_ENCRYPTION_KEY=.*|XEREX_CREDENTIALS_ENCRYPTION_KEY=$$ENC|" \
		    .env.example > .env; \
		echo "wrote .env"; )

# --- services ---------------------------------------------------------------
.PHONY: services-up
services-up: ## Start embedded PostgreSQL + Redis (no Docker required)
	$(PY) scripts/dev_services.py start

.PHONY: services-down
services-down: ## Stop the embedded services
	$(PY) scripts/dev_services.py stop

.PHONY: services-status
services-status: ## Report embedded service status
	$(PY) scripts/dev_services.py status

.PHONY: migrate
migrate: ## Apply database migrations
	cd $(BACKEND) && ../$(PY) -m alembic upgrade head

.PHONY: migration
migration: ## Create a migration: make migration m="add providers index"
	cd $(BACKEND) && ../$(PY) -m alembic revision --autogenerate -m "$(m)"

# --- development servers ----------------------------------------------------
.PHONY: api
api: ## Run the API with autoreload on :8000
	cd $(BACKEND) && ../$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --no-proxy-headers

.PHONY: web
web: ## Run the admin panel dev server on :5173
	cd $(FRONTEND) && npm run dev

# --- quality ----------------------------------------------------------------
.PHONY: test
test: test-backend test-frontend ## Run every test suite

.PHONY: test-backend
test-backend: ## Run backend tests
	cd $(BACKEND) && ../$(PY) -m pytest -q

.PHONY: test-frontend
test-frontend: ## Run frontend tests
	cd $(FRONTEND) && npm run test

.PHONY: lint
lint: ## Lint backend and frontend
	cd $(BACKEND) && ../$(VENV)/bin/ruff check app tests
	cd $(FRONTEND) && npm run lint

.PHONY: format
format: ## Format backend code
	cd $(BACKEND) && ../$(VENV)/bin/ruff format app tests alembic

.PHONY: typecheck
typecheck: ## Type-check the frontend
	cd $(FRONTEND) && npm run typecheck

.PHONY: build
build: ## Production build of the admin panel
	cd $(FRONTEND) && npm run build

# --- containers -------------------------------------------------------------
.PHONY: docker-up
docker-up: ## Start the full stack (production posture: no database ports published)
	docker compose up --build -d

.PHONY: docker-up-dev
docker-up-dev: ## Start the stack with the development override (localhost DB/cache ports)
	docker compose -f docker-compose.yml -f docker-compose.dev.yaml up --build -d

.PHONY: docker-down
docker-down: ## Stop the Docker Compose stack
	docker compose down

.PHONY: compose-check
compose-check: ## Validate compose structure and security posture (no Docker needed)
	cd $(BACKEND) && ../$(PY) -m pytest -q tests/test_compose_security.py

.PHONY: compose-config
compose-config: ## Render the merged compose configuration (requires Docker)
	docker compose -f docker-compose.yml config --quiet
	docker compose -f docker-compose.yml -f docker-compose.dev.yaml config --quiet
