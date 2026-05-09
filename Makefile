SHELL := /bin/bash

ROOT := $(CURDIR)
LOCAL_UV := $(ROOT)/.tools/uv/bin/uv
UV_BIN := $(shell command -v uv 2>/dev/null || printf "%s" "$(LOCAL_UV)")

BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000
FRONTEND_HOST ?= 127.0.0.1
FRONTEND_PORT ?= 5173
MCP_HOST ?= 127.0.0.1
MCP_PORT ?= 9000
MCP_PROVIDER_PORT_START ?= 9100
MCP_PROVIDER_IDS ?= ercot_market_data_transparency austin_water_utility_service_area twdb_water_data_for_texas texas_broadband_development_map travis_county_parcels texas_real_estate_research_center txgio_geospatial_catalog

.PHONY: help install backend-install frontend-install dev dev-all dev-web check-dev-ports check-web-ports backend-dev frontend-dev mcp-dev mcp-provider-dev mcp-providers-dev test test-e2e test-all lint frontend-build ensure-uv

help:
	@printf "Available targets:\n"
	@printf "  make install          Install backend and frontend dependencies\n"
	@printf "  make dev              Run FastAPI, Vite, and the MCP HTTP server together\n"
	@printf "  make dev-web          Run only FastAPI and Vite together\n"
	@printf "  make dev-all          Alias for make dev\n"
	@printf "  make backend-dev      Run only the FastAPI backend\n"
	@printf "  make frontend-dev     Run only the Vite frontend\n"
	@printf "  make mcp-dev          Run only the FastMCP HTTP server\n"
	@printf "  make mcp-provider-dev Run one provider MCP; pass PROVIDER_ID=...\n"
	@printf "  make mcp-providers-dev Run one MCP server per configured provider\n"
	@printf "  make test             Run backend tests and frontend build\n"
	@printf "  make test-e2e         Run Playwright end-to-end tests\n"
	@printf "  make test-all         Run backend, frontend, and Playwright tests\n"
	@printf "  make lint             Run backend lint checks\n"

install: backend-install frontend-install

backend-install: ensure-uv
	cd backend && "$(UV_BIN)" sync

frontend-install:
	cd frontend && npm install

dev: dev-all

dev-all: ensure-uv check-dev-ports
	@set -e; \
	backend_pid=""; \
	frontend_pid=""; \
	mcp_pid=""; \
	cleanup() { \
		if [ -n "$$backend_pid" ]; then kill "$$backend_pid" 2>/dev/null || true; fi; \
		if [ -n "$$frontend_pid" ]; then kill "$$frontend_pid" 2>/dev/null || true; fi; \
		if [ -n "$$mcp_pid" ]; then kill "$$mcp_pid" 2>/dev/null || true; fi; \
		wait 2>/dev/null || true; \
	}; \
	trap cleanup INT TERM EXIT; \
	( cd backend && "$(UV_BIN)" run fastapi dev app/main.py --host "$(BACKEND_HOST)" --port "$(BACKEND_PORT)" ) & \
	backend_pid=$$!; \
	( cd frontend && npm run dev -- --host "$(FRONTEND_HOST)" --port "$(FRONTEND_PORT)" ) & \
	frontend_pid=$$!; \
	( cd backend && MCP_HOST="$(MCP_HOST)" MCP_PORT="$(MCP_PORT)" "$(UV_BIN)" run python -m app.mcp ) & \
	mcp_pid=$$!; \
	wait

dev-web: ensure-uv check-web-ports
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

check-dev-ports:
	@for port in "$(BACKEND_PORT)" "$(FRONTEND_PORT)" "$(MCP_PORT)"; do \
		if lsof -nP -iTCP:$$port -sTCP:LISTEN >/dev/null 2>&1; then \
			printf "Port %s is already in use:\n" "$$port"; \
			lsof -nP -iTCP:$$port -sTCP:LISTEN; \
			printf "\nStop the existing process or override the port, e.g. BACKEND_PORT=8001 FRONTEND_PORT=5174 MCP_PORT=9001 make dev\n"; \
			exit 1; \
		fi; \
	done

check-web-ports:
	@for port in "$(BACKEND_PORT)" "$(FRONTEND_PORT)"; do \
		if lsof -nP -iTCP:$$port -sTCP:LISTEN >/dev/null 2>&1; then \
			printf "Port %s is already in use:\n" "$$port"; \
			lsof -nP -iTCP:$$port -sTCP:LISTEN; \
			printf "\nStop the existing process or override the port, e.g. BACKEND_PORT=8001 FRONTEND_PORT=5174 make dev-web\n"; \
			exit 1; \
		fi; \
	done

backend-dev: ensure-uv
	cd backend && "$(UV_BIN)" run fastapi dev app/main.py --host "$(BACKEND_HOST)" --port "$(BACKEND_PORT)"

frontend-dev:
	cd frontend && npm run dev -- --host "$(FRONTEND_HOST)" --port "$(FRONTEND_PORT)"

mcp-dev: ensure-uv
	cd backend && MCP_HOST="$(MCP_HOST)" MCP_PORT="$(MCP_PORT)" "$(UV_BIN)" run python -m app.mcp

mcp-provider-dev: ensure-uv
	@test -n "$(PROVIDER_ID)" || (printf "PROVIDER_ID is required\n" && exit 1)
	cd backend && PROVIDER_ID="$(PROVIDER_ID)" MCP_HOST="$(MCP_HOST)" MCP_PORT="$(MCP_PORT)" "$(UV_BIN)" run python -m app.mcp

mcp-providers-dev: ensure-uv
	@set -e; \
	pids=""; \
	cleanup() { \
		for pid in $$pids; do kill "$$pid" 2>/dev/null || true; done; \
		wait 2>/dev/null || true; \
	}; \
	trap cleanup INT TERM EXIT; \
	index=0; \
	for provider_id in $(MCP_PROVIDER_IDS); do \
		port=$$(( $(MCP_PROVIDER_PORT_START) + $$index )); \
		printf "Starting provider MCP %s at http://$(MCP_HOST):%s/mcp/\n" "$$provider_id" "$$port"; \
		( cd backend && PROVIDER_ID="$$provider_id" MCP_HOST="$(MCP_HOST)" MCP_PORT="$$port" "$(UV_BIN)" run python -m app.mcp ) & \
		pids="$$pids $$!"; \
		index=$$(( $$index + 1 )); \
	done; \
	wait

test: ensure-uv
	cd backend && "$(UV_BIN)" run pytest
	cd frontend && npm run build

test-e2e:
	cd frontend && npm run test:e2e

test-all: test test-e2e

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
