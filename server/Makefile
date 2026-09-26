.PHONY: help lint up up-isolation up-reverse-ssh test test-local coverage eval fixture-eval doctor release-audit stdio-bridge smoke-isolation smoke-isolation-tunnel smoke-reverse-ssh bootstrap-codex-auth bootstrap-claude-auth bootstrap-gemini-auth bootstrap-all-auth down config config-isolation config-reverse-ssh

help: ## Show available commands
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | sort

lint: ## Run Ruff checks across the whole repo
	# Repo-wide, not a path list: the previous scope (controller/app, controller/tests,
	# scripts/*.py) silently excluded client/, integrations/ and benchmarks/ — including
	# two packages published to PyPI — and four real errors had accumulated there unseen.
	# Ruff's defaults plus .gitignore already exclude .venv*/, node_modules/, build/, dist/.
	ruff check . --select E9,F,I

up: ## Start the local stack (docker removed)
	@echo "NOTE: docker compose stack removed; use scripts/start-local.ps1 for local runs."

up-isolation: ## (removed: docker-only isolation override)
	@echo "NOTE: docker isolation stack removed."

up-reverse-ssh: ## (removed: docker-only reverse-SSH sidecar)
	@echo "NOTE: reverse-SSH sidecar removed with docker stack."

test: ## (removed: docker-based controller tests)
	@echo "NOTE: docker test target removed; use 'make test-local'."

test-local: ## Run controller tests on the host with Python 3.10+
	./scripts/test_local.sh

coverage: ## Run controller tests with coverage on the host
	cd controller && python -m pytest tests/ --cov=app --cov-report=html --cov-report=term-missing

eval: ## Run the deterministic agent eval matrix without live providers
	python scripts/agent_eval.py --mock

fixture-eval: ## Validate local HTML eval fixtures
	python scripts/fixture_eval.py

doctor: ## Run the local readiness smoke
	./scripts/doctor.sh

release-audit: ## Run the launch-prep audit
	./scripts/release_audit.sh

stdio-bridge: ## Run the stdio MCP bridge against the local HTTP MCP endpoint
	./scripts/mcp_stdio_bridge.py

smoke-isolation: ## Removed: native shared_browser_node only
	@echo "NOTE: native only; use scripts/start-local.ps1 for local runs."

smoke-isolation-tunnel: ## Removed: native shared_browser_node only
	@echo "NOTE: native only; use scripts/start-local.ps1 for local runs."

smoke-reverse-ssh: ## Removed: reverse-SSH sidecar removed
	@echo "NOTE: native only; use scripts/start-local.ps1 for local runs."

bootstrap-codex-auth: ## Sign in Codex CLI inside the controller data volume
	./scripts/bootstrap_cli_auth.sh codex

bootstrap-claude-auth: ## Sign in Claude CLI inside the controller data volume
	./scripts/bootstrap_cli_auth.sh claude

bootstrap-gemini-auth: ## Sign in Gemini CLI inside the controller data volume
	./scripts/bootstrap_cli_auth.sh gemini

bootstrap-all-auth: ## Sign in all supported CLIs inside the controller data volume
	./scripts/bootstrap_cli_auth.sh all

down: ## (removed: docker compose stack removed)
	@echo "NOTE: docker compose stack removed; nothing to stop."

config: ## (removed: compose config deleted)
	@echo "NOTE: docker-compose.yml deleted."

config-isolation: ## (removed: isolation override deleted)
	@echo "NOTE: docker-compose.isolation.yml deleted."

config-reverse-ssh: ## (removed: reverse-SSH profile deleted)
	@echo "NOTE: reverse-SSH compose profile deleted."
