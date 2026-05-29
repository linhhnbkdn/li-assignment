import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.employee import Employee
from app.models.organization import OrgColumnConfig, Organization
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
    db: object,
    org: Organization,
):
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


def test_no_cross_org_data_leak(client: TestClient, token: str, db: object, org: Organization):
    other_org = Organization(id=str(uuid.uuid4()), name="Other Corp", secret="other-secret")
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
