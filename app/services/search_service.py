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
