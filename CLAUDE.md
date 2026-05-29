# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastAPI microservice for an HR company employee **search directory**. The assignment is defined in `idea/Technical assignment.md`.

**Scope**: Only the search/filter API. No CRUD for employees, no Add/Import/Export endpoints.

## Hard Constraints (from assignment)

- **Framework**: FastAPI (Python only)
- **No external dependencies** except for testing libraries — standard library + FastAPI + its minimal deps (Starlette, Pydantic, uvicorn)
- **Rate limiting**: must be a custom implementation, no external library (e.g. no `slowapi`, `limits`)
- **Containerized**: must include a `Dockerfile` (and ideally `docker-compose.yml`)
- **OpenAPI**: FastAPI auto-generates this; ensure it is accessible and accurate
- **Unit tested**: tests required for the search API

## Key Design Requirements

### Dynamic Columns
Column visibility is configured **per organization** (not per request). Store the config in DB or a config file — no CRUD API needed for this config. The API must only return columns configured for the requesting org, preventing data leaks.

### Performance (millions of users)
- Use pagination (limit/offset or cursor-based)
- Index DB columns used for filtering/searching (name, department, location, position, etc.)
- Consider full-text search (PostgreSQL `tsvector`/`GIN` index, or `ILIKE` with trigram index)

### Rate Limiting
Custom implementation — token bucket, sliding window, or fixed window counter stored in-memory or Redis. Must be applied at the API layer (middleware or dependency).

### No Data Leaks
- Never return columns not in the org's configured column set
- Never return employees from another org
- Filter at the DB query level, not post-fetch

## Commands

```bash
# Run the app (once set up)
uvicorn app.main:app --reload

# Run with Docker
docker compose up --build

# Run tests
pytest

# Run a single test file
pytest tests/test_search.py -v

# Run a single test
pytest tests/test_search.py::test_filter_by_department -v

# Lint / format
ruff check .
ruff format .
```

## Expected Project Structure

```
app/
  main.py          # FastAPI app, router includes
  routers/
    search.py      # GET /employees/search
  models/          # SQLAlchemy or raw SQL models
  schemas/         # Pydantic request/response schemas
  db.py            # DB connection / session
  config.py        # Settings (env vars via pydantic-settings)
  middleware/
    rate_limit.py  # Custom rate limiter
  services/
    search.py      # Business logic: query building, column filtering
tests/
  test_search.py
  test_rate_limit.py
docker-compose.yml
Dockerfile
README.md
pyproject.toml     # or requirements.txt
```

## Architecture Notes

- The org context (which org a request belongs to) must come from auth (e.g. API key → org_id lookup) or a request header — decide and be consistent
- Column config per org can live in the DB (`org_column_config` table) or a JSON/YAML file; DB is preferred for runtime flexibility
- The search endpoint should accept query params for each filterable field (name, department, location, position, email, etc.) and combine them with AND logic
- Response schema must be dynamic based on org column config — use a dict-based response or a Pydantic model with optional fields
