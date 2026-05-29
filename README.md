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

### Layer Overview

Strict 4-layer clean architecture — dependencies only flow **downward**. Upper layers never import from lower layers' peers.

```
┌─────────────────────────────────────────────┐
│  api/          HTTP layer                   │
│  (routes, Pydantic schemas, DI deps)        │
└────────────────────┬────────────────────────┘
                     │ calls
┌────────────────────▼────────────────────────┐
│  services/     Business logic layer         │
│  (search orchestration, column masking)     │
└────────────────────┬────────────────────────┘
                     │ calls
┌────────────────────▼────────────────────────┐
│  repos/        Data access layer            │
│  (SQLAlchemy ORM queries, FTS5 raw SQL)     │
└────────────────────┬────────────────────────┘
                     │ calls
┌────────────────────▼────────────────────────┐
│  core/         Cross-cutting concerns       │
│  (auth, rate limiter, config, logging, db)  │
└─────────────────────────────────────────────┘
```

Each layer has a **base class** — `BaseRepository`, `BaseService`, `BaseSchema` — enforcing a consistent interface contract.

### Project Structure

```
app/
├── main.py                     # App factory + lifespan (rate limiter init)
├── api/
│   ├── schemas/
│   │   ├── base.py             # BaseSchema (from_attributes, extra=forbid)
│   │   ├── search.py           # SearchParams, EmployeeRow, SearchResponse
│   │   └── auth.py             # TokenPayload
│   └── v1/
│       ├── deps.py             # get_current_user, require_rate_limit (DI chain)
│       └── routes/search.py   # GET /api/v1/employees/search
├── services/
│   ├── base.py                 # BaseService(ABC)
│   └── search_service.py      # Column masking + pagination orchestration
├── repos/
│   ├── base.py                 # BaseRepository(ABC) — holds Session
│   ├── org_repo.py             # Org + column config lookups
│   └── employee_repo.py       # Search: ORM filters + FTS5 raw SQL
├── models/
│   ├── base.py                 # DeclarativeBase (Alembic target)
│   ├── organization.py        # Organization, OrgColumnConfig
│   ├── employee.py            # Employee + composite indexes
│   └── user.py                # User
└── core/
    ├── config.py               # Settings via pydantic-settings + env vars
    ├── logging.py              # configure_logging() — called once at startup
    ├── db.py                   # Engine, SessionLocal, get_db (WAL + FK pragma)
    ├── auth.py                 # JWT: unverified decode → org secret lookup → verify
    └── rate_limiter.py        # SlidingWindowRateLimiter (threading.Lock, no external libs)

alembic/versions/0001_initial.py  # Tables + FTS5 virtual table + 3 triggers
tests/
├── conftest.py                 # In-memory SQLite fixtures, JWT helpers, TestClient
├── test_rate_limiter.py       # Unit: sliding window correctness
├── test_search_service.py     # Unit: column masking, cursor logic
└── test_search_route.py       # Integration: auth, filters, pagination, 401/429
```

### Key Design Decisions

**Multi-tenancy & security**
- Every DB query is scoped to `org_id` extracted from the verified JWT — no employee from another org can leak into results.
- Column visibility is configured per org in `org_column_configs` (JSON array). The service layer strips disallowed fields before Pydantic serialization — the repo never knows what's masked.
- `id` and `name` are always returned regardless of org config.

**JWT auth — per-org secret**
```
Request → decode unverified → extract org_id
       → fetch org from DB → get org.secret
       → verify JWT with org.secret → fetch User
```
Compromise of one org's secret does not affect other orgs.

**Search — two paths**

| Condition | Strategy |
|---|---|
| `?q=` present | FTS5 virtual table (`employees_fts MATCH :q*`) joined to employees via `rowid` |
| filters only | SQLAlchemy ORM query with composite indexed columns |

FTS5 index is kept in sync automatically via three SQLite triggers (INSERT / UPDATE / DELETE on `employees`).

**Pagination — keyset (cursor-based)**

Uses `WHERE id > :after_id ORDER BY id` instead of `LIMIT/OFFSET`. At millions of rows, `OFFSET N` requires scanning N rows on every page — keyset pagination is O(1) regardless of page depth.

**Rate limiting — custom sliding window**

No external library. Pure Python using `collections.deque` per user + `threading.Lock`:
- Each request pops timestamps older than the window, then checks count ≥ limit.
- `retry_after` is calculated from the oldest timestamp still in the window.
- Stored in-memory on `app.state` — resets on restart (intentional for a demo; swap with Redis for production).

**Database — SQLite + WAL mode**

WAL (Write-Ahead Logging) is enabled on every connection via a SQLAlchemy event listener. This allows concurrent reads while a write is in progress — critical for search-heavy workloads.

### Data Model

```
organizations          org_column_configs
──────────────         ──────────────────
id (PK)                org_id (PK, FK)
name                   columns  ← JSON: ["name","email","department",...]
secret  ← JWT key
        │
        ├── users
        │   ──────
        │   id (PK) ← JWT sub
        │   org_id (FK)
        │   email
        │
        └── employees
            ──────────────────────────────────────────
            id (PK)           ← cursor key
            org_id (FK)       ← ix_emp_org
            name              ← FTS5 indexed
            email             ← FTS5 indexed
            phone
            department        ← ix_emp_org_dept (org_id, department)
            location          ← ix_emp_org_loc  (org_id, location)
            position          ← ix_emp_org_pos  (org_id, position)

employees_fts  ← FTS5 virtual table (content=employees)
               ← synced via INSERT/UPDATE/DELETE triggers
```
