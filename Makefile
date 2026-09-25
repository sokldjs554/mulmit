# Common tasks. `make help` lists them.
.DEFAULT_GOAL := help
API := apps/api
WEB := apps/web
ANCHOR ?= 2026-09-25
SCALE ?= 1.0

.PHONY: help
help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Install API (uv) and web (pnpm) dependencies
	cd $(API) && uv sync
	cd $(WEB) && pnpm install --frozen-lockfile

.PHONY: infra
infra: ## Start PostgreSQL (pgvector), Redis and Mailpit only
	docker compose up -d db redis mailpit

.PHONY: up
up: ## Build and start the whole stack in Docker
	docker compose up -d --build

.PHONY: down
down: ## Stop the stack (keeps volumes)
	docker compose down

.PHONY: demo
demo: ## Migrate, seed the synthetic world and run the full pipeline (local Python)
	cd $(API) && uv run manage db upgrade
	cd $(API) && uv run manage seed --anchor $(ANCHOR) --scale $(SCALE)
	cd $(API) && uv run manage demo run

.PHONY: api
api: ## Run the API with reload on :8000
	cd $(API) && APP_LOG_JSON=false uv run uvicorn app.api.app:create_app --factory --reload --port 8000

.PHONY: worker
worker: ## Run the arq worker (cron + queue)
	cd $(API) && APP_LOG_JSON=false uv run manage worker

.PHONY: web
web: ## Run the Next.js dev server on :3000
	cd $(WEB) && API_ORIGIN=http://localhost:8000 pnpm dev

.PHONY: lint
lint: ## Ruff, mypy, ESLint and tsc
	cd $(API) && uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd $(WEB) && pnpm lint && pnpm typecheck

.PHONY: test
test: ## API tests (needs `make infra`) and web unit tests
	cd $(API) && uv run pytest
	cd $(WEB) && pnpm test

.PHONY: eval
eval: ## Evaluate extraction/linking/OCR against ground truth and write docs/evaluation.md
	cd $(API) && uv run manage eval all --record --report ../../docs/evaluation.md

.PHONY: check-sources
check-sources: ## First real call to each 조달청 operation (needs APP_DATA_GO_KR_SERVICE_KEY) → docs/source-check.md
	cd $(API) && uv run manage sources check --report ../../docs/source-check.md > /dev/null

.PHONY: eval-llm
eval-llm: ## Compare Claude models/efforts on the hand-written set (needs ANTHROPIC_API_KEY, ~$5; see --dry-run)
	mkdir -p .data && cd $(API) && uv run manage eval llm --report ../../docs/evaluation-llm.md > ../../.data/eval-llm.json

.PHONY: bench
bench: ## Hot-query plans at production-like volume → docs/performance.md (few minutes)
	cd $(API) && uv run manage bench --report ../../docs/performance.md

.PHONY: gen-api
gen-api: ## Regenerate the web app's OpenAPI types from the FastAPI schema
	cd $(WEB) && pnpm gen:api
