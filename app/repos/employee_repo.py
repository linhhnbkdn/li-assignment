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
