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
