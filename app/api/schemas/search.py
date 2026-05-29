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
