SHELL := /bin/bash

ROOT := $(CURDIR)
LOCAL_UV := $(ROOT)/.tools/uv/bin/uv
UV_BIN := $(shell command -v uv 2>/dev/null || printf "%s" "$(LOCAL_UV)")

BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000
FRONTEND_HOST ?= 127.0.0.1
FRONTEND_PORT ?= 5173

.PHONY: help install backend-install frontend-install dev backend-dev frontend-dev test lint frontend-build ensure-uv

help:
	@printf "Available targets:\n"
	@printf "  make install          Install backend and frontend dependencies\n"
	@printf "  make dev              Run FastAPI and Vite together\n"
	@printf "  make backend-dev      Run only the FastAPI backend\n"
	@printf "  make frontend-dev     Run only the Vite frontend\n"
	@printf "  make test             Run backend tests and frontend build\n"
	@printf "  make lint             Run backend lint checks\n"

install: backend-install frontend-install

backend-install: ensure-uv
	cd backend && "$(UV_BIN)" sync

frontend-install:
	cd frontend && npm install

dev: ensure-uv
	@set -e; \
	backend_pid=""; \
	frontend_pid=""; \
	cleanup() { \
		if [ -n "$$backend_pid" ]; then kill "$$backend_pid" 2>/dev/null || true; fi; \
		if [ -n "$$frontend_pid" ]; then kill "$$frontend_pid" 2>/dev/null || true; fi; \
		wait 2>/dev/null || true; \
	}; \
	trap cleanup INT TERM EXIT; \
	( cd backend && "$(UV_BIN)" run fastapi dev app/main.py --host "$(BACKEND_HOST)" --port "$(BACKEND_PORT)" ) & \
	backend_pid=$$!; \
	( cd frontend && npm run dev -- --host "$(FRONTEND_HOST)" --port "$(FRONTEND_PORT)" ) & \
	frontend_pid=$$!; \
	wait

backend-dev: ensure-uv
	cd backend && "$(UV_BIN)" run fastapi dev app/main.py --host "$(BACKEND_HOST)" --port "$(BACKEND_PORT)"

frontend-dev:
	cd frontend && npm run dev -- --host "$(FRONTEND_HOST)" --port "$(FRONTEND_PORT)"

test: ensure-uv
	cd backend && "$(UV_BIN)" run pytest
	cd frontend && npm run build

lint: ensure-uv
	cd backend && "$(UV_BIN)" run ruff check .

frontend-build:
	cd frontend && npm run build

ensure-uv:
	@if command -v uv >/dev/null 2>&1; then \
		exit 0; \
	fi; \
	if [ ! -x "$(LOCAL_UV)" ]; then \
		printf "uv not found; installing a repo-local uv at .tools/uv...\n"; \
		python3 -m venv "$(ROOT)/.tools/uv"; \
		"$(ROOT)/.tools/uv/bin/python" -m pip install --quiet uv; \
	fi

