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
