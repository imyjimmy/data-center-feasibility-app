# Backend

FastAPI service for parcel feasibility data APIs.

## Commands

```sh
uv sync
uv run fastapi dev app/main.py
uv run pytest
uv run ruff check .
```

## Endpoints

- `GET /health`: service health check
- `GET /api/project-question`: the MVP question this app is built to answer

