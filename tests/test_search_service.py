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
