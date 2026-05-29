from sqlalchemy import Column, ForeignKey, Index, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    name = Column(String, nullable=False)
    email = Column(String)
    phone = Column(String)
    department = Column(String)
    location = Column(String)
    position = Column(String)

    organization = relationship("Organization", back_populates="employees")

    __table_args__ = (
        Index("ix_emp_org", "org_id"),
        Index("ix_emp_org_dept", "org_id", "department"),
        Index("ix_emp_org_loc", "org_id", "location"),
        Index("ix_emp_org_pos", "org_id", "position"),
    )
