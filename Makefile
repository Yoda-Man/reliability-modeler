# Reliability Modeler — build, test, release and operate.
#
#   make help
#
# VERSION is read from modeler/__init__.py (single source of truth).
# Nothing here reads .env directly: docker compose loads .env itself, so
# secrets never end up in make's environment.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

VERSION            := $(shell sed -nE 's/^__version__[[:space:]]*=[[:space:]]*["'"'"']([^"'"'"']+)["'"'"'].*/\1/p' modeler/__init__.py)
# Override per call (.env is not read): make push DOCKERHUB_USERNAME=<you>
DOCKERHUB_USERNAME ?= trustaldo
REGISTRY           ?= docker.io
PREFIX             := $(REGISTRY)/$(DOCKERHUB_USERNAME)/reliability-modeler
PLATFORMS          ?= linux/amd64,linux/arm64
BUILDER            ?= reliability-modeler-builder
BACKUP_DIR         ?= ./backups
PYTHON             ?= python3

# Local images use the same names compose pulls, tagged with VERSION.
LOCAL_API := $(DOCKERHUB_USERNAME)/reliability-modeler-api:$(VERSION)
LOCAL_UI  := $(DOCKERHUB_USERNAME)/reliability-modeler-ui:$(VERSION)

.PHONY: help version build build-api build-ui test test-python test-ui smoke \
        push _require-version _confirm-push _buildx up down logs backup restore clean

help: ## Show this help
	@echo ""
	@echo "  Reliability Modeler $(VERSION)"
	@echo ""
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	    awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-10s %s\n", $$1, $$2}'
	@echo ""
	@echo "  Variables: DOCKERHUB_USERNAME=$(DOCKERHUB_USERNAME) PLATFORMS=$(PLATFORMS)"
	@echo "             BACKUP_DIR=$(BACKUP_DIR)  (restore: make restore FILE=<archive>)"
	@echo ""

version: ## Print the version from modeler/__init__.py
	@echo "$(VERSION)"

_require-version:
	@if [ -z "$(VERSION)" ]; then echo "ERROR: could not read __version__ from modeler/__init__.py" >&2; exit 1; fi

# ── Build (local, current architecture) ──────────────────────────────────────
build: build-api build-ui ## Build both images locally (current arch), tagged :VERSION

build-api: _require-version
	docker build -f web/api/Dockerfile -t $(LOCAL_API) .

build-ui: _require-version
	docker build -f web/ui/Dockerfile -t $(LOCAL_UI) ./web/ui

# ── Test ─────────────────────────────────────────────────────────────────────
test: test-python test-ui ## Run Python unit tests (with coverage) and UI tests

test-python:
	$(PYTHON) -m pytest tests --ignore=tests/integration \
	    --cov=modeler --cov=web/api --cov-report=term-missing

test-ui:
	cd web/ui && npm test

smoke: _require-version ## Run scripts/smoke-test.sh against locally built :VERSION images
	IMAGE_TAG=$(VERSION) DOCKERHUB_NAMESPACE=$(DOCKERHUB_USERNAME) ./scripts/smoke-test.sh

# ── Release (multi-arch push to Docker Hub) ──────────────────────────────────
push: _require-version _confirm-push _buildx ## Build multi-arch and push :VERSION and :latest (both images)
	docker buildx build --builder $(BUILDER) --platform $(PLATFORMS) \
	    -f web/api/Dockerfile \
	    -t $(PREFIX)-api:$(VERSION) -t $(PREFIX)-api:latest \
	    --push .
	docker buildx build --builder $(BUILDER) --platform $(PLATFORMS) \
	    -f web/ui/Dockerfile \
	    -t $(PREFIX)-ui:$(VERSION) -t $(PREFIX)-ui:latest \
	    --push ./web/ui
	@echo "Pushed $(PREFIX)-{api,ui}:{$(VERSION),latest} for $(PLATFORMS)"

_confirm-push:
	@echo ""
	@echo "  About to build ($(PLATFORMS)) and push:"
	@echo "    $(PREFIX)-api:$(VERSION)  and :latest"
	@echo "    $(PREFIX)-ui:$(VERSION)   and :latest"
	@if [ -n "$$(git status --porcelain 2>/dev/null)" ]; then echo "  WARNING: working tree has uncommitted changes."; fi
	@echo ""
	@read -r -p "  Push to Docker Hub? [y/N] " CONFIRM; \
	    case "$$CONFIRM" in [yY]|[yY][eE][sS]) ;; *) echo "Aborted."; exit 1;; esac

_buildx:
	@docker buildx inspect $(BUILDER) >/dev/null 2>&1 || \
	    docker buildx create --name $(BUILDER) --driver docker-container >/dev/null
	@docker buildx inspect --bootstrap $(BUILDER) >/dev/null

# ── Operate (uses .env in the repo root) ─────────────────────────────────────
up: ## docker compose up -d (requires .env)
	docker compose up -d

down: ## docker compose down (volumes are kept)
	docker compose down

logs: ## Follow logs of both services
	docker compose logs -f --tail=200

backup: ## Archive output_data + config_data volumes into BACKUP_DIR
	./scripts/backup.sh "$(BACKUP_DIR)"

restore: ## Restore volumes from FILE=<archive> (stack must be stopped)
	@if [ -z "$(FILE)" ]; then echo "usage: make restore FILE=backups/<archive>.tar.gz" >&2; exit 1; fi
	./scripts/restore.sh "$(FILE)"

clean: ## Remove local reliability-modeler images and Python/UI caches
	-docker images --format '{{.Repository}}:{{.Tag}}' | grep 'reliability-modeler-' | xargs -r docker rmi 2>/dev/null
	rm -rf .pytest_cache .coverage htmlcov coverage.xml web/ui/.next
	find . -path ./web/ui/node_modules -prune -o -name __pycache__ -type d -prune -exec rm -rf {} +
