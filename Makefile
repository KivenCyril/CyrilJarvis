.PHONY: help install dev test lint format clean docker-build docker-up docker-down run demo docs benchmark

# --- Variables ---
PYTHON := .venv/bin/python
PYTEST := .venv/bin/python -m pytest
UV := uv

# ==============================================================================
# Help
# ==============================================================================

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ==============================================================================
# Setup
# ==============================================================================

install: ## Install dependencies
	$(UV) venv
	$(UV) pip install -e ".[all]" --python .venv/bin/python

dev: ## Install dev dependencies
	$(UV) pip install -e ".[all]" --python .venv/bin/python
	$(UV) pip install pytest pytest-asyncio httpx ruff mypy --python .venv/bin/python

setup: ## Run first-time setup script
	bash scripts/setup.sh

# ==============================================================================
# Development
# ==============================================================================

run: ## Start the JARVIS server
	$(PYTHON) -m uvicorn jarvis.server.app:app --host 127.0.0.1 --port 8000 --reload

run-tui: ## Start the interactive TUI
	$(PYTHON) -c "import asyncio; from jarvis.tui.app import run_tui; asyncio.run(run_tui())"

demo: ## Run the demo script
	$(PYTHON) demo.py

shell: ## Open a Python shell with JARVIS loaded
	$(PYTHON) -c "import asyncio; from jarvis.app import JarvisApp; app=JarvisApp(); asyncio.run(app.initialize()); print('JARVIS ready. Use: app.chat(), app.run_spec(), etc.'); import code; code.interact(local={'app': app, 'asyncio': asyncio})"

# ==============================================================================
# Testing
# ==============================================================================

test: ## Run all tests
	$(PYTEST) tests/ -v --tb=short

test-fast: ## Run tests without slow tests
	$(PYTEST) tests/ -v --tb=short -m "not slow" -x

test-coverage: ## Run tests with coverage
	$(PYTEST) tests/ --cov=jarvis --cov-report=term-missing --cov-report=html

test-stress: ## Run stress tests only
	$(PYTEST) tests/test_stress.py -v --tb=short

test-integration: ## Run integration tests only
	$(PYTEST) tests/test_integration.py tests/test_cross_module.py -v --tb=short

# ==============================================================================
# Code Quality
# ==============================================================================

lint: ## Run linter
	$(PYTHON) -m ruff check src/ tests/

format: ## Format code
	$(PYTHON) -m ruff format src/ tests/

typecheck: ## Run type checker
	$(PYTHON) -m mypy src/jarvis --ignore-missing-imports

check: lint typecheck ## Run all checks (lint + typecheck)

# ==============================================================================
# Documentation
# ==============================================================================

docs: ## Generate API documentation
	$(PYTHON) -c "from jarvis.docs import generate_api_docs; generate_api_docs('docs')"
	@echo "Documentation generated in docs/"

docs-serve: ## Serve documentation locally
	$(PYTHON) -m http.server 8080 --directory docs

# ==============================================================================
# Benchmarks
# ==============================================================================

benchmark: ## Run performance benchmarks
	$(PYTHON) -c "import asyncio; from jarvis.benchmarks import run_benchmarks; asyncio.run(run_benchmarks(50))"

benchmark-full: ## Run full benchmark suite with script
	bash scripts/benchmark.sh

# ==============================================================================
# Docker
# ==============================================================================

docker-build: ## Build Docker image
	docker build -t jarvis:latest .

docker-up: ## Start with docker-compose
	docker compose up -d

docker-up-full: ## Start with all optional services
	docker compose --profile full up -d

docker-up-local: ## Start with local LLM (Ollama)
	docker compose --profile local-llm up -d

docker-down: ## Stop docker-compose
	docker compose down

docker-down-clean: ## Stop and remove volumes
	docker compose down -v

docker-logs: ## View docker logs
	docker compose logs -f jarvis

docker-shell: ## Shell into the running container
	docker compose exec jarvis /bin/bash

# ==============================================================================
# System Info
# ==============================================================================

info: ## Show system information
	$(PYTHON) -m jarvis.cli.main info

diagnostics: ## Run system diagnostics
	$(PYTHON) -c "import asyncio; from jarvis.diagnostics import SystemDiagnostics; d=SystemDiagnostics(); r=asyncio.run(d.run_all()); print(r.to_table())"

# ==============================================================================
# Cleanup
# ==============================================================================

clean: ## Clean build artifacts
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

clean-all: clean ## Clean everything including venv and data
	rm -rf .venv/ docs/ ~/.jarvis/

# ==============================================================================
# Statistics
# ==============================================================================

stats: ## Show project statistics
	@echo "=== JARVIS Project Statistics ==="
	@echo "Source files: $$(find src -name '*.py' | wc -l | tr -d ' ')"
	@echo "Source LOC:   $$(find src -name '*.py' -exec cat {} \; | wc -l | tr -d ' ')"
	@echo "Test files:   $$(find tests -name '*.py' | wc -l | tr -d ' ')"
	@echo "Test LOC:     $$(find tests -name '*.py' -exec cat {} \; | wc -l | tr -d ' ')"
	@echo "HTML LOC:     $$(find web -name '*.html' -exec cat {} \; 2>/dev/null | wc -l | tr -d ' ')"
	@echo "Skills:       $$(find skills -name '*.yaml' 2>/dev/null | wc -l | tr -d ' ')"
	@echo "Modules:      $$(ls -d src/jarvis/*/ 2>/dev/null | grep -v __pycache__ | wc -l | tr -d ' ')"
	@echo "Total tests:  $$($(PYTEST) tests/ --co -q 2>/dev/null | tail -1)"
