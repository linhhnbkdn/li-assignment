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
