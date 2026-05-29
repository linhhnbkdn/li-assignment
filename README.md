# HR Employee Search API

FastAPI microservice providing a multi-tenant employee search directory.

## Quick Start

### Docker (recommended)

```bash
docker compose up --build
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

### Local

```bash
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
python seed.py        # seeds demo data + prints JWT tokens
uvicorn app.main:app --reload
```

## Authentication

All endpoints require a Bearer JWT token. Run `seed.py` to get demo tokens.

```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/employees/search?department=Engineering&limit=5"
```

## Search API

`GET /api/v1/employees/search`

| Param | Type | Description |
|---|---|---|
| `q` | string | Full-text search on name + email |
| `department` | string | Exact filter |
| `location` | string | Exact filter |
| `position` | string | Exact filter |
| `limit` | int | Page size (1–100, default 20) |
| `after_id` | string | Cursor for next page |

## Run Tests

```bash
pytest tests/ -v
```

## Rate Limiting

30 requests per 60 seconds per user (configurable via `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW` env vars). Returns `HTTP 429` with `Retry-After` header.

## Architecture

Clean 4-layer architecture:
- `api/` — HTTP routes, Pydantic schemas, FastAPI dependencies
- `services/` — business logic (search, column masking)
- `repos/` — data access (SQLAlchemy ORM + FTS5 raw SQL)
- `core/` — cross-cutting (JWT auth, rate limiter, config, logging)
