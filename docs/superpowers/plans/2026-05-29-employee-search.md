# Employee Search Microservice — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI employee search directory microservice with per-org column masking, JWT auth, custom rate limiting, and SQLite + FTS5 for full-text search.

**Architecture:** Clean 4-layer architecture (api → services → repos → core) where each layer has a base class and dependencies only flow downward. Cross-cutting concerns (auth, rate limiter, config, logging) live in `core/` and can be imported by any layer.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (sync), Alembic, SQLite + FTS5, PyJWT, pydantic-settings, pytest + httpx

---

## File Map

| File | Responsibility |
|---|---|
| `app/core/config.py` | Pydantic Settings — reads env vars |
| `app/core/logging.py` | `configure_logging()` — called once at startup |
| `app/core/db.py` | Engine, `SessionLocal`, `get_db` generator |
| `app/core/auth.py` | JWT decode/verify against per-org secret |
| `app/core/rate_limiter.py` | `SlidingWindowRateLimiter` — in-memory, thread-safe |
| `app/models/base.py` | `Base(DeclarativeBase)` — Alembic target |
| `app/models/organization.py` | `Organization`, `OrgColumnConfig` ORM models |
| `app/models/employee.py` | `Employee` ORM model + composite indexes |
| `app/models/user.py` | `User` ORM model |
| `app/repos/base.py` | `BaseRepository(ABC)` — holds `Session` |
| `app/repos/org_repo.py` | Org + column config lookups |
| `app/repos/employee_repo.py` | Search query builder, FTS5, keyset pagination |
| `app/services/base.py` | `BaseService(ABC)` |
| `app/services/search_service.py` | Filter orchestration + column masking |
| `app/api/schemas/base.py` | `BaseSchema(BaseModel)` with shared config |
| `app/api/schemas/search.py` | `SearchParams`, `EmployeeRow`, `SearchResponse` |
| `app/api/schemas/auth.py` | `TokenPayload` |
| `app/api/v1/deps.py` | `get_db`, `get_current_user`, `require_rate_limit` |
| `app/api/v1/routes/search.py` | `GET /api/v1/employees/search` |
| `app/main.py` | App factory, middleware, lifespan |
| `alembic/env.py` | Alembic config pointing at `Base.metadata` |
| `alembic/versions/0001_initial.py` | All tables + FTS5 virtual table + triggers |
| `tests/conftest.py` | In-memory SQLite fixtures, JWT helpers, `TestClient` |
| `tests/test_rate_limiter.py` | Unit tests for sliding window |
| `tests/test_search_service.py` | Unit tests for filter + masking |
| `tests/test_search_route.py` | Integration tests via `TestClient` |
| `seed.py` | Seed demo orgs + 100k employees |
| `Dockerfile` | Production image |
| `docker-compose.yml` | App service |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`, `app/api/__init__.py`, `app/api/v1/__init__.py`, `app/api/v1/routes/__init__.py`, `app/api/schemas/__init__.py`, `app/services/__init__.py`, `app/repos/__init__.py`, `app/models/__init__.py`, `app/core/__init__.py`
- Create: `tests/__init__.py`
- Create: `.env.example`

- [ ] **Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "hr-search"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "sqlalchemy>=2.0.0",
    "alembic>=1.13.0",
    "pyjwt>=2.8.0",
    "pydantic-settings>=2.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "httpx>=0.27.0",
    "faker>=24.0.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Create all `__init__.py` files (all empty)**

```bash
mkdir -p app/api/v1/routes app/api/schemas app/services app/repos app/models app/core tests
touch app/__init__.py
touch app/api/__init__.py app/api/v1/__init__.py app/api/v1/routes/__init__.py app/api/schemas/__init__.py
touch app/services/__init__.py app/repos/__init__.py app/models/__init__.py app/core/__init__.py
touch tests/__init__.py
```

- [ ] **Create `.env.example`**

```ini
DATABASE_URL=sqlite:///./hr.db
JWT_SECRET=change-me-in-production
RATE_LIMIT_REQUESTS=30
RATE_LIMIT_WINDOW=60
LOG_LEVEL=INFO
APP_ENV=development
```

- [ ] **Install dependencies**

```bash
pip install -e ".[dev]"
```

- [ ] **Commit**

```bash
git add pyproject.toml .env.example app/ tests/
git commit -m "chore: project scaffolding and dependencies"
```

---

## Task 2: Core — Config + Logging

**Files:**
- Create: `app/core/config.py`
- Create: `app/core/logging.py`

- [ ] **Write `app/core/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./hr.db"
    jwt_secret: str = "dev-secret"
    rate_limit_requests: int = 30
    rate_limit_window: int = 60
    log_level: str = "INFO"
    app_env: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
```

- [ ] **Write `app/core/logging.py`**

```python
import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
```

- [ ] **Commit**

```bash
git add app/core/config.py app/core/logging.py
git commit -m "feat: core config and logging"
```

---

## Task 3: Core — Database

**Files:**
- Create: `app/core/db.py`

- [ ] **Write `app/core/db.py`**

```python
import logging
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=settings.app_env == "development",
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Commit**

```bash
git add app/core/db.py
git commit -m "feat: SQLAlchemy engine and session factory"
```

---

## Task 4: ORM Models

**Files:**
- Create: `app/models/base.py`
- Create: `app/models/organization.py`
- Create: `app/models/employee.py`
- Create: `app/models/user.py`

- [ ] **Write `app/models/base.py`**

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Write `app/models/organization.py`**

```python
from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    secret = Column(String, nullable=False)

    column_config = relationship(
        "OrgColumnConfig",
        back_populates="organization",
        uselist=False,
    )
    employees = relationship("Employee", back_populates="organization")
    users = relationship("User", back_populates="organization")


class OrgColumnConfig(Base):
    __tablename__ = "org_column_configs"

    org_id = Column(String, ForeignKey("organizations.id"), primary_key=True)
    columns = Column(String, nullable=False)  # JSON array string

    organization = relationship("Organization", back_populates="column_config")
```

- [ ] **Write `app/models/employee.py`**

```python
from sqlalchemy import Column, ForeignKey, Index, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    name = Column(String, nullable=False)
    email = Column(String)
    phone = Column(String)
    department = Column(String)
    location = Column(String)
    position = Column(String)

    organization = relationship("Organization", back_populates="employees")

    __table_args__ = (
        Index("ix_emp_org", "org_id"),
        Index("ix_emp_org_dept", "org_id", "department"),
        Index("ix_emp_org_loc", "org_id", "location"),
        Index("ix_emp_org_pos", "org_id", "position"),
    )
```

- [ ] **Write `app/models/user.py`**

```python
from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    email = Column(String, nullable=False, unique=True)

    organization = relationship("Organization", back_populates="users")
```

- [ ] **Commit**

```bash
git add app/models/
git commit -m "feat: SQLAlchemy ORM models"
```

---

## Task 5: Alembic Setup + Initial Migration

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/0001_initial.py`

- [ ] **Init Alembic**

```bash
alembic init alembic
```

- [ ] **Replace `alembic/env.py`**

```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.models.base import Base
from app.models import employee, organization, user  # noqa: F401 — register models

config = context.config
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL", "sqlite:///./hr.db"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Create `alembic/versions/0001_initial.py`**

```python
"""initial

Revision ID: 0001
Revises:
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("secret", sa.String(), nullable=False),
    )
    op.create_table(
        "org_column_configs",
        sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("columns", sa.String(), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email", sa.String(), nullable=False, unique=True),
    )
    op.create_table(
        "employees",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String()),
        sa.Column("phone", sa.String()),
        sa.Column("department", sa.String()),
        sa.Column("location", sa.String()),
        sa.Column("position", sa.String()),
    )
    op.create_index("ix_emp_org", "employees", ["org_id"])
    op.create_index("ix_emp_org_dept", "employees", ["org_id", "department"])
    op.create_index("ix_emp_org_loc", "employees", ["org_id", "location"])
    op.create_index("ix_emp_org_pos", "employees", ["org_id", "position"])

    # FTS5 virtual table for full-text search on name + email
    op.execute("""
        CREATE VIRTUAL TABLE employees_fts USING fts5(
            name, email,
            content=employees,
            content_rowid=rowid
        )
    """)
    # Triggers to keep FTS index in sync
    op.execute("""
        CREATE TRIGGER employees_ai AFTER INSERT ON employees BEGIN
            INSERT INTO employees_fts(rowid, name, email)
            VALUES (new.rowid, new.name, new.email);
        END
    """)
    op.execute("""
        CREATE TRIGGER employees_ad AFTER DELETE ON employees BEGIN
            INSERT INTO employees_fts(employees_fts, rowid, name, email)
            VALUES ('delete', old.rowid, old.name, old.email);
        END
    """)
    op.execute("""
        CREATE TRIGGER employees_au AFTER UPDATE ON employees BEGIN
            INSERT INTO employees_fts(employees_fts, rowid, name, email)
            VALUES ('delete', old.rowid, old.name, old.email);
            INSERT INTO employees_fts(rowid, name, email)
            VALUES (new.rowid, new.name, new.email);
        END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS employees_au")
    op.execute("DROP TRIGGER IF EXISTS employees_ad")
    op.execute("DROP TRIGGER IF EXISTS employees_ai")
    op.execute("DROP TABLE IF EXISTS employees_fts")
    op.drop_table("employees")
    op.drop_table("users")
    op.drop_table("org_column_configs")
    op.drop_table("organizations")
```

- [ ] **Run migration**

```bash
alembic upgrade head
```

Expected output ends with: `Running upgrade  -> 0001, initial`

- [ ] **Commit**

```bash
git add alembic/ alembic.ini
git commit -m "feat: Alembic setup and initial migration with FTS5"
```

---

## Task 6: Base Classes (repos + services + schemas)

**Files:**
- Create: `app/repos/base.py`
- Create: `app/services/base.py`
- Create: `app/api/schemas/base.py`

- [ ] **Write `app/repos/base.py`**

```python
from abc import ABC

from sqlalchemy.orm import Session


class BaseRepository(ABC):
    def __init__(self, db: Session) -> None:
        self.db = db
```

- [ ] **Write `app/services/base.py`**

```python
from abc import ABC


class BaseService(ABC):
    pass
```

- [ ] **Write `app/api/schemas/base.py`**

```python
from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        populate_by_name=True,
    )
```

- [ ] **Commit**

```bash
git add app/repos/base.py app/services/base.py app/api/schemas/base.py
git commit -m "feat: base classes for repos, services, and schemas"
```

---

## Task 7: Rate Limiter

**Files:**
- Create: `app/core/rate_limiter.py`
- Create: `tests/test_rate_limiter.py`

- [ ] **Write failing tests first — `tests/test_rate_limiter.py`**

```python
import time

import pytest

from app.core.rate_limiter import RateLimitExceeded, SlidingWindowRateLimiter


def test_allows_requests_under_limit():
    limiter = SlidingWindowRateLimiter(limit=3, window_seconds=60)
    limiter.check("user-1")
    limiter.check("user-1")
    limiter.check("user-1")  # 3rd — still ok


def test_raises_on_limit_exceeded():
    limiter = SlidingWindowRateLimiter(limit=3, window_seconds=60)
    limiter.check("user-1")
    limiter.check("user-1")
    limiter.check("user-1")
    with pytest.raises(RateLimitExceeded):
        limiter.check("user-1")  # 4th — exceeded


def test_different_users_isolated():
    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60)
    limiter.check("user-1")
    limiter.check("user-2")  # different user — should not raise


def test_window_resets_old_requests(monkeypatch):
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=10)
    fake_time = [0.0]
    monkeypatch.setattr("app.core.rate_limiter.time.monotonic", lambda: fake_time[0])

    limiter.check("user-1")
    limiter.check("user-1")

    fake_time[0] = 11.0  # advance past window
    limiter.check("user-1")  # old requests expired — should not raise


def test_retry_after_is_positive():
    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60)
    limiter.check("user-1")
    with pytest.raises(RateLimitExceeded) as exc_info:
        limiter.check("user-1")
    assert exc_info.value.retry_after > 0
```

- [ ] **Run tests — expect failure**

```bash
pytest tests/test_rate_limiter.py -v
```

Expected: `ImportError` or `ModuleNotFoundError`

- [ ] **Write `app/core/rate_limiter.py`**

```python
import logging
import threading
import time
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s.")


class SlidingWindowRateLimiter:
    def __init__(self, limit: int = 30, window_seconds: int = 60) -> None:
        self._limit = limit
        self._window = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, user_id: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets[user_id]
            cutoff = now - self._window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._limit:
                retry_after = int(self._window - (now - bucket[0])) + 1
                logger.warning(f"Rate limit exceeded: user_id={user_id}")
                raise RateLimitExceeded(retry_after=retry_after)
            bucket.append(now)
```

- [ ] **Run tests — expect all pass**

```bash
pytest tests/test_rate_limiter.py -v
```

Expected: 5 passed

- [ ] **Commit**

```bash
git add app/core/rate_limiter.py tests/test_rate_limiter.py
git commit -m "feat: sliding-window rate limiter with unit tests"
```

---

## Task 8: Auth (JWT)

**Files:**
- Create: `app/core/auth.py`
- Create: `app/api/schemas/auth.py`

- [ ] **Write `app/api/schemas/auth.py`**

```python
from app.api.schemas.base import BaseSchema


class TokenPayload(BaseSchema):
    model_config = BaseSchema.model_config.copy()

    sub: str      # user_id
    org_id: str
    exp: int
```

- [ ] **Write `app/core/auth.py`**

```python
import logging

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

logger = logging.getLogger(__name__)


class AuthError(Exception):
    pass


def decode_token_unverified(token: str) -> dict:
    """Decode without verification to extract org_id for secret lookup."""
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except Exception as exc:
        raise AuthError("Malformed token") from exc


def decode_token(token: str, secret: str) -> dict:
    """Decode and verify with the org's secret."""
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except ExpiredSignatureError as exc:
        raise AuthError("Token expired") from exc
    except InvalidTokenError as exc:
        raise AuthError("Invalid token") from exc
```

- [ ] **Commit**

```bash
git add app/core/auth.py app/api/schemas/auth.py
git commit -m "feat: JWT auth helpers"
```

---

## Task 9: Pydantic Schemas (Search)

**Files:**
- Create: `app/api/schemas/search.py`

- [ ] **Write `app/api/schemas/search.py`**

```python
from pydantic import Field

from app.api.schemas.base import BaseSchema


class SearchParams(BaseSchema):
    model_config = BaseSchema.model_config.copy()

    q: str | None = Field(default=None, description="Full-text search on name and email")
    department: str | None = Field(default=None, description="Filter by department")
    location: str | None = Field(default=None, description="Filter by location")
    position: str | None = Field(default=None, description="Filter by position")
    limit: int = Field(default=20, ge=1, le=100, description="Page size")
    after_id: str | None = Field(default=None, description="Cursor: last seen employee id")


class EmployeeRow(BaseSchema):
    model_config = BaseSchema.model_config.copy()

    id: str
    name: str
    email: str | None = None
    phone: str | None = None
    department: str | None = None
    location: str | None = None
    position: str | None = None


class SearchResponse(BaseSchema):
    model_config = BaseSchema.model_config.copy()

    items: list[EmployeeRow]
    next_cursor: str | None = None
```

- [ ] **Commit**

```bash
git add app/api/schemas/search.py
git commit -m "feat: Pydantic search request/response schemas"
```

---

## Task 10: Repositories

**Files:**
- Create: `app/repos/org_repo.py`
- Create: `app/repos/employee_repo.py`

- [ ] **Write `app/repos/org_repo.py`**

```python
import json
import logging

from sqlalchemy.orm import Session

from app.models.organization import OrgColumnConfig, Organization
from app.repos.base import BaseRepository

logger = logging.getLogger(__name__)


class OrgRepository(BaseRepository):
    def __init__(self, db: Session) -> None:
        super().__init__(db=db)

    def get_by_id(self, org_id: str) -> Organization | None:
        return self.db.get(Organization, org_id)

    def get_column_config(self, org_id: str) -> list[str]:
        config = self.db.get(OrgColumnConfig, org_id)
        if config is None:
            logger.warning(f"No column config for org_id={org_id}, returning defaults")
            return ["name", "email", "department", "location", "position"]
        return json.loads(config.columns)
```

- [ ] **Write `app/repos/employee_repo.py`**

```python
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.repos.base import BaseRepository

logger = logging.getLogger(__name__)

_FILTERABLE_COLUMNS = {"department", "location", "position"}


class EmployeeRepository(BaseRepository):
    def __init__(self, db: Session) -> None:
        super().__init__(db=db)

    def search(
        self,
        org_id: str,
        q: str | None = None,
        department: str | None = None,
        location: str | None = None,
        position: str | None = None,
        limit: int = 20,
        after_id: str | None = None,
    ) -> list[Employee]:
        if q:
            return self._search_fts(
                org_id=org_id,
                q=q,
                department=department,
                location=location,
                position=position,
                limit=limit,
                after_id=after_id,
            )
        return self._search_filtered(
            org_id=org_id,
            department=department,
            location=location,
            position=position,
            limit=limit,
            after_id=after_id,
        )

    def _search_filtered(
        self,
        org_id: str,
        department: str | None,
        location: str | None,
        position: str | None,
        limit: int,
        after_id: str | None,
    ) -> list[Employee]:
        query = self.db.query(Employee).filter(Employee.org_id == org_id)
        if department:
            query = query.filter(Employee.department == department)
        if location:
            query = query.filter(Employee.location == location)
        if position:
            query = query.filter(Employee.position == position)
        if after_id:
            query = query.filter(Employee.id > after_id)
        return query.order_by(Employee.id).limit(limit).all()

    def _search_fts(
        self,
        org_id: str,
        q: str,
        department: str | None,
        location: str | None,
        position: str | None,
        limit: int,
        after_id: str | None,
    ) -> list[Employee]:
        params: dict = {"org_id": org_id, "q": f"{q}*", "limit": limit}
        filters = ["e.org_id = :org_id"]
        if department:
            filters.append("e.department = :department")
            params["department"] = department
        if location:
            filters.append("e.location = :location")
            params["location"] = location
        if position:
            filters.append("e.position = :position")
            params["position"] = position
        if after_id:
            filters.append("e.id > :after_id")
            params["after_id"] = after_id

        where_clause = " AND ".join(filters)
        sql = text(f"""
            SELECT e.*
            FROM employees e
            JOIN employees_fts fts ON fts.rowid = e.rowid
            WHERE employees_fts MATCH :q
            AND {where_clause}
            ORDER BY e.id
            LIMIT :limit
        """)
        rows = self.db.execute(sql, params).fetchall()
        return [self.db.get(Employee, row.id) for row in rows]
```

- [ ] **Commit**

```bash
git add app/repos/org_repo.py app/repos/employee_repo.py
git commit -m "feat: org and employee repositories with FTS5 search"
```

---

## Task 11: Search Service + Unit Tests

**Files:**
- Create: `app/services/search_service.py`
- Create: `tests/test_search_service.py`

- [ ] **Write failing tests — `tests/test_search_service.py`**

```python
import json
from unittest.mock import MagicMock

import pytest

from app.services.search_service import SearchService


def make_employee(**kwargs):
    defaults = dict(
        id="emp-1",
        org_id="org-1",
        name="Alice Nguyen",
        email="alice@acme.com",
        phone="0901234567",
        department="Engineering",
        location="Ho Chi Minh",
        position="Senior Backend",
    )
    defaults.update(kwargs)
    emp = MagicMock()
    for k, v in defaults.items():
        setattr(emp, k, v)
    return emp


@pytest.fixture()
def mock_employee_repo():
    repo = MagicMock()
    repo.search.return_value = [make_employee()]
    return repo


@pytest.fixture()
def mock_org_repo():
    repo = MagicMock()
    repo.get_column_config.return_value = ["name", "email", "department"]
    return repo


def test_search_returns_masked_columns(mock_employee_repo, mock_org_repo):
    service = SearchService(
        employee_repo=mock_employee_repo,
        org_repo=mock_org_repo,
    )
    result = service.search(org_id="org-1", q=None, department=None, location=None, position=None, limit=20, after_id=None)

    assert len(result.items) == 1
    row = result.items[0]
    assert row.name == "Alice Nguyen"
    assert row.email == "alice@acme.com"
    assert row.department == "Engineering"
    # phone and location not in column config
    assert row.phone is None
    assert row.location is None
    assert row.position is None


def test_next_cursor_set_when_full_page(mock_employee_repo, mock_org_repo):
    employees = [make_employee(id=f"emp-{i}") for i in range(3)]
    mock_employee_repo.search.return_value = employees
    service = SearchService(
        employee_repo=mock_employee_repo,
        org_repo=mock_org_repo,
    )
    result = service.search(org_id="org-1", q=None, department=None, location=None, position=None, limit=3, after_id=None)
    assert result.next_cursor == "emp-2"


def test_next_cursor_none_when_partial_page(mock_employee_repo, mock_org_repo):
    mock_employee_repo.search.return_value = [make_employee()]
    service = SearchService(
        employee_repo=mock_employee_repo,
        org_repo=mock_org_repo,
    )
    result = service.search(org_id="org-1", q=None, department=None, location=None, position=None, limit=20, after_id=None)
    assert result.next_cursor is None


def test_name_always_included_even_if_not_in_config(mock_employee_repo, mock_org_repo):
    mock_org_repo.get_column_config.return_value = ["department"]  # no "name"
    service = SearchService(
        employee_repo=mock_employee_repo,
        org_repo=mock_org_repo,
    )
    result = service.search(org_id="org-1", q=None, department=None, location=None, position=None, limit=20, after_id=None)
    assert result.items[0].name == "Alice Nguyen"
```

- [ ] **Run tests — expect failure**

```bash
pytest tests/test_search_service.py -v
```

Expected: `ImportError`

- [ ] **Write `app/services/search_service.py`**

```python
import logging

from app.api.schemas.search import EmployeeRow, SearchResponse
from app.repos.employee_repo import EmployeeRepository
from app.repos.org_repo import OrgRepository
from app.services.base import BaseService

logger = logging.getLogger(__name__)

_MASKABLE_COLUMNS = {"email", "phone", "department", "location", "position"}


class SearchService(BaseService):
    def __init__(
        self,
        employee_repo: EmployeeRepository,
        org_repo: OrgRepository,
    ) -> None:
        self._employee_repo = employee_repo
        self._org_repo = org_repo

    def search(
        self,
        org_id: str,
        q: str | None,
        department: str | None,
        location: str | None,
        position: str | None,
        limit: int,
        after_id: str | None,
    ) -> SearchResponse:
        allowed_cols = self._org_repo.get_column_config(org_id=org_id)
        employees = self._employee_repo.search(
            org_id=org_id,
            q=q,
            department=department,
            location=location,
            position=position,
            limit=limit,
            after_id=after_id,
        )
        items = [self._mask(employee=emp, allowed_cols=allowed_cols) for emp in employees]
        next_cursor = employees[-1].id if len(employees) == limit else None
        return SearchResponse(items=items, next_cursor=next_cursor)

    def _mask(self, employee, allowed_cols: list[str]) -> EmployeeRow:
        data: dict = {"id": employee.id, "name": employee.name}
        for col in _MASKABLE_COLUMNS:
            if col in allowed_cols:
                data[col] = getattr(employee, col, None)
        return EmployeeRow.model_validate(data)
```

- [ ] **Run tests — expect all pass**

```bash
pytest tests/test_search_service.py -v
```

Expected: 5 passed

- [ ] **Commit**

```bash
git add app/services/search_service.py tests/test_search_service.py
git commit -m "feat: search service with column masking and pagination (TDD)"
```

---

## Task 12: FastAPI Dependencies

**Files:**
- Create: `app/api/v1/deps.py`

- [ ] **Write `app/api/v1/deps.py`**

```python
import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.core.auth import AuthError, decode_token, decode_token_unverified
from app.core.db import get_db
from app.core.rate_limiter import RateLimitExceeded
from app.models.user import User
from app.repos.org_repo import OrgRepository
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        unverified = decode_token_unverified(token=token)
        org_id = unverified.get("org_id")
        if not org_id:
            raise credentials_exc

        org_repo = OrgRepository(db=db)
        org = org_repo.get_by_id(org_id=org_id)
        if org is None:
            raise credentials_exc

        payload = decode_token(token=token, secret=org.secret)
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exc

        user = db.get(User, user_id)
        if user is None or user.org_id != org_id:
            raise credentials_exc

        return user
    except AuthError:
        raise credentials_exc


def require_rate_limit(
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    limiter = request.app.state.rate_limiter
    try:
        limiter.check(user_id=user.id)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Retry after {exc.retry_after}s.",
            headers={"Retry-After": str(exc.retry_after)},
        )
```

- [ ] **Commit**

```bash
git add app/api/v1/deps.py
git commit -m "feat: FastAPI dependency injection (auth + rate limit)"
```

---

## Task 13: Search Route

**Files:**
- Create: `app/api/v1/routes/search.py`

- [ ] **Write `app/api/v1/routes/search.py`**

```python
import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas.search import SearchParams, SearchResponse
from app.api.v1.deps import get_current_user, require_rate_limit
from app.core.db import get_db
from app.models.user import User
from app.repos.employee_repo import EmployeeRepository
from app.repos.org_repo import OrgRepository
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Search employees",
    description="Search and filter employees within the authenticated user's organization.",
)
def search_employees(
    params: Annotated[SearchParams, Depends()],
    user: User = Depends(get_current_user),
    _: None = Depends(require_rate_limit),
    db: Session = Depends(get_db),
) -> SearchResponse:
    logger.info(f"Search request: user_id={user.id} org_id={user.org_id} params={params}")
    service = SearchService(
        employee_repo=EmployeeRepository(db=db),
        org_repo=OrgRepository(db=db),
    )
    return service.search(
        org_id=user.org_id,
        q=params.q,
        department=params.department,
        location=params.location,
        position=params.position,
        limit=params.limit,
        after_id=params.after_id,
    )
```

- [ ] **Commit**

```bash
git add app/api/v1/routes/search.py
git commit -m "feat: search route wired to service"
```

---

## Task 14: App Factory

**Files:**
- Create: `app/main.py`

- [ ] **Write `app/main.py`**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.routes import search
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.rate_limiter import SlidingWindowRateLimiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(level=settings.log_level)
    app.state.rate_limiter = SlidingWindowRateLimiter(
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window,
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="HR Employee Search API",
        description="Search directory for HR organizations",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(search.router, prefix="/api/v1")
    return app


app = create_app()
```

- [ ] **Verify app starts**

```bash
uvicorn app.main:app --reload
```

Expected: server starts on `http://127.0.0.1:8000`. Open `http://127.0.0.1:8000/docs` — should show the search endpoint. Ctrl+C to stop.

- [ ] **Commit**

```bash
git add app/main.py
git commit -m "feat: FastAPI app factory with lifespan"
```

---

## Task 15: Integration Tests

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_search_route.py`

- [ ] **Write `tests/conftest.py`**

```python
import json
import uuid
from collections.abc import Generator

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import get_db
from app.core.rate_limiter import SlidingWindowRateLimiter
from app.main import create_app
from app.models.base import Base
from app.models.employee import Employee
from app.models.organization import OrgColumnConfig, Organization
from app.models.user import User

TEST_DB_URL = "sqlite://"  # in-memory

_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
_TestingSessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    connection = _engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


ORG_SECRET = "test-secret"


@pytest.fixture()
def org(db: Session) -> Organization:
    o = Organization(id=str(uuid.uuid4()), name="Acme Corp", secret=ORG_SECRET)
    db.add(o)
    config = OrgColumnConfig(
        org_id=o.id,
        columns=json.dumps(["name", "email", "department", "location", "position"]),
    )
    db.add(config)
    db.flush()
    return o


@pytest.fixture()
def user(db: Session, org: Organization) -> User:
    u = User(id=str(uuid.uuid4()), org_id=org.id, email="alice@acme.com")
    db.add(u)
    db.flush()
    return u


@pytest.fixture()
def token(user: User, org: Organization) -> str:
    return jwt.encode(
        {"sub": user.id, "org_id": org.id, "exp": 9999999999},
        ORG_SECRET,
        algorithm="HS256",
    )


@pytest.fixture()
def employees(db: Session, org: Organization) -> list[Employee]:
    emps = [
        Employee(
            id=str(uuid.uuid4()),
            org_id=org.id,
            name=f"Employee {i}",
            email=f"emp{i}@acme.com",
            phone="0900000000",
            department="Engineering" if i % 2 == 0 else "Marketing",
            location="Ho Chi Minh",
            position="Engineer",
        )
        for i in range(5)
    ]
    for e in emps:
        db.add(e)
    db.flush()
    return emps


@pytest.fixture()
def client(db: Session) -> TestClient:
    app = create_app()
    app.state.rate_limiter = SlidingWindowRateLimiter(limit=1000, window_seconds=60)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)
```

- [ ] **Write `tests/test_search_route.py`**

```python
import pytest
from fastapi.testclient import TestClient

from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_search_returns_200(client: TestClient, token: str, employees: list[Employee]):
    response = client.get("/api/v1/employees/search", headers=auth(token))
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert len(body["items"]) == 5


def test_search_filters_by_department(client: TestClient, token: str, employees: list[Employee]):
    response = client.get(
        "/api/v1/employees/search",
        params={"department": "Engineering"},
        headers=auth(token),
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert all(item["department"] == "Engineering" for item in items)


def test_search_pagination(client: TestClient, token: str, employees: list[Employee]):
    r1 = client.get("/api/v1/employees/search", params={"limit": 2}, headers=auth(token))
    assert r1.status_code == 200
    body1 = r1.json()
    assert len(body1["items"]) == 2
    assert body1["next_cursor"] is not None

    r2 = client.get(
        "/api/v1/employees/search",
        params={"limit": 2, "after_id": body1["next_cursor"]},
        headers=auth(token),
    )
    assert r2.status_code == 200
    ids1 = {i["id"] for i in body1["items"]}
    ids2 = {i["id"] for i in r2.json()["items"]}
    assert ids1.isdisjoint(ids2)


def test_no_token_returns_401(client: TestClient):
    response = client.get("/api/v1/employees/search")
    assert response.status_code == 401


def test_invalid_token_returns_401(client: TestClient):
    response = client.get("/api/v1/employees/search", headers=auth("bad.token.here"))
    assert response.status_code == 401


def test_rate_limit_returns_429(client: TestClient, token: str, employees: list[Employee]):
    from app.core.rate_limiter import SlidingWindowRateLimiter
    client.app.state.rate_limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60)

    client.get("/api/v1/employees/search", headers=auth(token))  # 1st — ok
    response = client.get("/api/v1/employees/search", headers=auth(token))  # 2nd — blocked
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_column_masking_respects_org_config(
    client: TestClient,
    token: str,
    employees: list[Employee],
    db,
    org: Organization,
):
    import json
    from app.models.organization import OrgColumnConfig
    config = db.get(OrgColumnConfig, org.id)
    config.columns = json.dumps(["name", "department"])
    db.flush()

    response = client.get("/api/v1/employees/search", headers=auth(token))
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert "name" in item
    assert "department" in item
    assert item.get("email") is None
    assert item.get("phone") is None
    assert item.get("location") is None


def test_no_cross_org_data_leak(client: TestClient, token: str, db, org: Organization):
    import uuid
    import json
    from app.models.organization import Organization as Org, OrgColumnConfig
    from app.models.employee import Employee

    other_org = Org(id=str(uuid.uuid4()), name="Other Corp", secret="other-secret")
    db.add(other_org)
    other_config = OrgColumnConfig(
        org_id=other_org.id,
        columns=json.dumps(["name", "email"]),
    )
    db.add(other_config)
    other_emp = Employee(
        id=str(uuid.uuid4()),
        org_id=other_org.id,
        name="Secret Employee",
        email="secret@other.com",
        department="Secret Dept",
        location="Secret City",
        position="Secret Role",
    )
    db.add(other_emp)
    db.flush()

    response = client.get("/api/v1/employees/search", headers=auth(token))
    names = [i["name"] for i in response.json()["items"]]
    assert "Secret Employee" not in names
```

- [ ] **Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests pass (note: FTS5 tests skip on in-memory SQLite since FTS5 virtual table creation requires the Alembic migration — only the `_search_filtered` path is exercised in tests; FTS5 is exercised against the real DB via seed + manual test)

- [ ] **Commit**

```bash
git add tests/conftest.py tests/test_search_route.py
git commit -m "feat: integration tests for search route (auth, pagination, masking, rate limit)"
```

---

## Task 16: Seed Script

**Files:**
- Create: `seed.py`

- [ ] **Write `seed.py`**

```python
"""Seed the database with demo orgs, users, and 100k employees."""
import json
import random
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.db import SessionLocal, engine
from app.models.base import Base
from app.models.employee import Employee
from app.models.organization import OrgColumnConfig, Organization
from app.models.user import User

DEPARTMENTS = ["Engineering", "Marketing", "Sales", "HR", "Finance", "Operations", "Legal"]
LOCATIONS = ["Ho Chi Minh", "Ha Noi", "Da Nang", "Can Tho", "Singapore", "Remote"]
POSITIONS = ["Junior", "Mid-level", "Senior", "Lead", "Manager", "Director", "VP"]
FIRST_NAMES = ["Linh", "Minh", "Anh", "Hoa", "Long", "Nam", "Thu", "Lan", "Duc", "Phuong"]
LAST_NAMES = ["Nguyen", "Tran", "Le", "Pham", "Hoang", "Vo", "Dinh", "Do", "Bui", "Ngo"]

ORGS = [
    {
        "id": "org-acme",
        "name": "Acme Corp",
        "secret": "acme-secret-key",
        "columns": ["name", "email", "department", "location", "position"],
    },
    {
        "id": "org-globex",
        "name": "Globex",
        "secret": "globex-secret-key",
        "columns": ["name", "department", "location"],
    },
]


def seed(db: Session, employee_count: int = 100_000) -> None:
    print("Seeding organizations...")
    for org_data in ORGS:
        org = Organization(
            id=org_data["id"],
            name=org_data["name"],
            secret=org_data["secret"],
        )
        db.merge(org)
        config = OrgColumnConfig(
            org_id=org_data["id"],
            columns=json.dumps(org_data["columns"]),
        )
        db.merge(config)

        user = User(
            id=f"user-{org_data['id']}",
            org_id=org_data["id"],
            email=f"admin@{org_data['name'].lower().replace(' ', '')}.com",
        )
        db.merge(user)

    db.flush()
    print(f"Seeding {employee_count} employees...")
    batch_size = 1000
    for i in range(0, employee_count, batch_size):
        batch = []
        for j in range(batch_size):
            org_id = random.choice([o["id"] for o in ORGS])
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            idx = i + j
            emp = Employee(
                id=str(uuid.uuid4()),
                org_id=org_id,
                name=f"{first} {last}",
                email=f"{first.lower()}.{last.lower()}{idx}@example.com",
                phone=f"09{random.randint(10000000, 99999999)}",
                department=random.choice(DEPARTMENTS),
                location=random.choice(LOCATIONS),
                position=random.choice(POSITIONS),
            )
            batch.append(emp)
        db.bulk_save_objects(batch)
        db.flush()
        if (i // batch_size) % 10 == 0:
            print(f"  {i + batch_size:,} / {employee_count:,}")

    db.commit()
    print("Done.")
    for org_data in ORGS:
        import jwt as pyjwt
        token = pyjwt.encode(
            {"sub": f"user-{org_data['id']}", "org_id": org_data["id"], "exp": 9999999999},
            org_data["secret"],
            algorithm="HS256",
        )
        print(f"\n{org_data['name']} token:\n  {token}")


if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db=db)
```

- [ ] **Run seed**

```bash
alembic upgrade head && python seed.py
```

Expected: prints progress + two JWT tokens you can use with `curl` or Swagger UI.

- [ ] **Commit**

```bash
git add seed.py
git commit -m "feat: seed script with 100k employees and demo JWT tokens"
```

---

## Task 17: Docker

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Write `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY . .

RUN alembic upgrade head && python seed.py

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Write `docker-compose.yml`**

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite:///./hr.db
      - JWT_SECRET=dev-secret
      - RATE_LIMIT_REQUESTS=30
      - RATE_LIMIT_WINDOW=60
      - LOG_LEVEL=INFO
      - APP_ENV=production
    volumes:
      - db_data:/app

volumes:
  db_data:
```

- [ ] **Write `.dockerignore`**

```
.git
__pycache__
*.pyc
*.pyo
.env
.pytest_cache
tests/
*.db
```

- [ ] **Build and verify**

```bash
docker compose up --build
```

Expected: API running on `http://localhost:8000`. Open `http://localhost:8000/docs`.

- [ ] **Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: Docker containerization"
```

---

## Task 18: README

**Files:**
- Create: `README.md`

- [ ] **Write `README.md`**

```markdown
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

30 requests per 60 seconds per user (configurable via env vars). Returns `HTTP 429` with `Retry-After` header.
```

- [ ] **Commit**

```bash
git add README.md
git commit -m "docs: README with quick start and API reference"
```

---

## Self-Review Checklist

- [x] **JWT auth** — per-org secret, 2-query verify flow (Task 8, 12)
- [x] **Rate limiting** — custom sliding window, no external lib, per user (Task 7)
- [x] **Column masking** — `_mask()` in service layer, `id`+`name` always present (Task 11)
- [x] **FTS5** — migration creates virtual table + triggers (Task 5), used in `_search_fts()` (Task 10)
- [x] **Keyset pagination** — `WHERE id > :after_id ORDER BY id` (Task 10)
- [x] **No cross-org data leak** — `org_id` filter on every query + masked output (Tasks 10, 11, 15)
- [x] **Base classes** — `BaseRepository`, `BaseService`, `BaseSchema` (Task 6)
- [x] **Logging** — `configure_logging()` called in lifespan, per-module loggers (Tasks 2, 14)
- [x] **Alembic** — versioned migration with FTS5 virtual table (Task 5)
- [x] **Docker** — Dockerfile + docker-compose + .dockerignore (Task 17)
- [x] **OpenAPI** — auto-generated at `/docs` by FastAPI
- [x] **Tests** — unit (rate limiter, service) + integration (route) (Tasks 7, 11, 15)
