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
