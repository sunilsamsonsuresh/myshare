# MyShare developer commands. Python goes through uv; the web app uses npm.
# Ports: API 8000 · MCP server 8001 · Host 8002 · Web 5173
SHELL := /bin/bash
.DEFAULT_GOAL := help
UV := uv run --env-file .env

.PHONY: help setup seed dev dev-offline api mcp host fake-host web test test-py test-web lint fmt typecheck inspector token e2e injection smoke clean

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-11s\033[0m %s\n", $$1, $$2}'

setup: ## Install Python (uv) and web (npm) dependencies, create .env
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example; set ANTHROPIC_API_KEY")
	uv sync --all-packages
	@if [ -f apps/web/package.json ]; then cd apps/web && npm install; fi

seed: ## Reset the database and load demo data
	$(UV) python -m myshare_api.seed

api: ## Run the REST API on :8000
	$(UV) uvicorn myshare_api.main:app --port 8000 --reload --reload-dir apps/api

mcp: ## Run the MCP server (Streamable HTTP) on :8001
	$(UV) python -m myshare_mcp --transport http --port 8001

host: ## Run the host (LangGraph agent + MCP client) on :8002
	$(UV) uvicorn myshare_host.main:app --port 8002 --reload --reload-dir apps/host

fake-host: ## Run the host with an offline keyword "model" (no API key needed)
	$(UV) python scripts/fake_host.py

web: ## Run the Vite dev server on :5173
	cd apps/web && npm run dev

dev: ## Run API, MCP server, host and web together (Ctrl+C stops all)
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) --no-print-directory api 2>&1 | sed -u 's/^/[api]  /' & \
	$(MAKE) --no-print-directory mcp 2>&1 | sed -u 's/^/[mcp]  /' & \
	$(MAKE) --no-print-directory host 2>&1 | sed -u 's/^/[host] /' & \
	$(MAKE) --no-print-directory web 2>&1 | sed -u 's/^/[web]  /' & \
	wait

dev-offline: ## Like `dev`, but the host uses the offline keyword model
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) --no-print-directory api 2>&1 | sed -u 's/^/[api]  /' & \
	$(MAKE) --no-print-directory mcp 2>&1 | sed -u 's/^/[mcp]  /' & \
	$(MAKE) --no-print-directory fake-host 2>&1 | sed -u 's/^/[host] /' & \
	$(MAKE) --no-print-directory web 2>&1 | sed -u 's/^/[web]  /' & \
	wait

test: test-py test-web ## Run all tests

test-py: ## Run Python tests
	uv run pytest -q

test-web: ## Run frontend tests
	@if [ -f apps/web/package.json ]; then cd apps/web && npm test -- --run; fi

lint: ## Lint Python (ruff) and web (eslint)
	uv run ruff check .
	uv run ruff format --check .
	@if [ -f apps/web/package.json ]; then cd apps/web && npm run lint; fi

fmt: ## Auto-format Python
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## Type-check Python (pyright) and web (tsc)
	uv run pyright
	@if [ -f apps/web/package.json ]; then cd apps/web && npx tsc -b --noEmit; fi

inspector: ## Open the MCP Inspector against the running MCP server
	@echo "Connect with Transport=Streamable HTTP, URL=http://localhost:8001/mcp"
	@echo "Add header  Authorization: Bearer <token>  (get one with: make token)"
	npx -y @modelcontextprotocol/inspector

token: ## Print a JWT for the demo user (for the Inspector / curl)
	@$(UV) python scripts/get_token.py

e2e: ## End-to-end chat demo: add an expense via chat + approval (needs `make dev` running)
	$(UV) python scripts/e2e_demo.py

injection: ## Prompt-injection demo against the running stack (then `make seed` to clean up)
	$(UV) python scripts/injection_demo.py

smoke: ## Host smoke test over real HTTP with a scripted LLM (needs api + mcp running)
	$(UV) python scripts/smoke_host.py

clean: ## Remove local databases and caches
	rm -f myshare.db host_checkpoints.db logs/mcp_wire.jsonl
	rm -rf .pytest_cache .ruff_cache
