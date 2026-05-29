from abc import ABC

from sqlalchemy.orm import Session


class BaseRepository(ABC):
    def __init__(self, db: Session) -> None:
        self.db = db
