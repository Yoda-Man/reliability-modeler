# Reliability Modeler — Docker Workflow
#
# This Makefile automates building and pushing Docker images to Docker Hub.
# Modeled after the AnchorStay workflow.

# Load .env so variables are available to recipes
ifneq (,$(wildcard .env))
    include .env
    export
endif

# ── Defaults ──────────────────────────────────────────────────────────────────
DOCKERHUB_USERNAME ?= $(error Set DOCKERHUB_USERNAME in .env or pass on command line)
IMAGE_TAG          ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo "latest")
PLATFORM           ?= linux/amd64
REGISTRY           ?= docker.io
PREFIX             := $(REGISTRY)/$(DOCKERHUB_USERNAME)/reliability-modeler

.PHONY: help build build-api build-ui push push-api push-ui clean

help:
	@echo ""
	@echo "  Reliability Modeler — Docker Workflow"
	@echo ""
	@echo "  make build              Build all Docker images (tag: $(IMAGE_TAG))"
	@echo "  make push               Push all images to Docker Hub"
	@echo "  make clean              Remove local images"
	@echo ""

# ── Build ─────────────────────────────────────────────────────────────────────
build: build-api build-ui
	@echo "✓ All images built with tag: $(IMAGE_TAG)"

build-api:
	@echo "→ Building API image..."
	docker build --platform $(PLATFORM) \
		-f web/api/Dockerfile \
		-t reliability-modeler-api:$(IMAGE_TAG) \
		-t $(PREFIX)-api:$(IMAGE_TAG) \
		.
	@echo "✓ reliability-modeler-api:$(IMAGE_TAG)"

build-ui:
	@echo "→ Building UI image..."
	docker build --platform $(PLATFORM) \
		-f web/ui/Dockerfile \
		-t reliability-modeler-ui:$(IMAGE_TAG) \
		-t $(PREFIX)-ui:$(IMAGE_TAG) \
		./web/ui
	@echo "✓ reliability-modeler-ui:$(IMAGE_TAG)"

# ── Push ──────────────────────────────────────────────────────────────────────
push: _confirm-push push-api push-ui
	@echo "✓ All images pushed with tag: $(IMAGE_TAG)"

push-api: _docker-login
	@echo "→ Pushing API..."
	docker push $(PREFIX)-api:$(IMAGE_TAG)

push-ui: _docker-login
	@echo "→ Pushing UI..."
	docker push $(PREFIX)-ui:$(IMAGE_TAG)

# ── Private helpers ───────────────────────────────────────────────────────────
_confirm-push:
	@echo ""
	@echo "  About to push:"
	@echo "    $(PREFIX)-api:$(IMAGE_TAG)"
	@echo "    $(PREFIX)-ui:$(IMAGE_TAG)"
	@echo ""
	@read -r -p "  Push to Docker Hub? [y/N] " CONFIRM && \
	    [[ "$$CONFIRM" =~ ^[Yy](es)?$$ ]] || (echo "Aborted."; exit 1)

_docker-login:
	@docker info 2>/dev/null | grep -q "Username" || docker login

clean:
	docker image prune -f
	docker images | grep reliability-modeler | awk '{print $$3}' | xargs docker rmi -f 2>/dev/null || true
	@echo "✓ Local images removed"
