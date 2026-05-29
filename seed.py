"""Seed the database with demo orgs, users, and 100k employees."""
import json
import random
import uuid

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.employee import Employee
from app.models.organization import OrgColumnConfig, Organization
from app.models.user import User

DEPARTMENTS = ["Engineering", "Marketing", "Sales", "HR", "Finance", "Operations", "Legal"]
LOCATIONS = ["Ho Chi Minh", "Ha Noi", "Da Nang", "Can Tho", "Singapore", "Remote"]
POSITIONS = ["Junior", "Mid-level", "Senior", "Lead", "Manager", "Director", "VP"]
FIRST_NAMES = ["Linh", "Minh", "Anh", "Hoa", "Long", "Nam", "Thu", "Lan", "Duc", "Phuong"]
LAST_NAMES = ["Nguyen", "Tran", "Le", "Pham", "Hoang", "Vo", "Dinh", "Do", "Bui", "Ngo"]

ORGS = [
    {
        "id": "org-acme",
        "name": "Acme Corp",
        "secret": "acme-secret-key",
        "columns": ["name", "email", "department", "location", "position"],
    },
    {
        "id": "org-globex",
        "name": "Globex",
        "secret": "globex-secret-key",
        "columns": ["name", "department", "location"],
    },
]


def seed(db: Session, employee_count: int = 100_000) -> None:
    print("Seeding organizations...")
    for org_data in ORGS:
        org = Organization(
            id=org_data["id"],
            name=org_data["name"],
            secret=org_data["secret"],
        )
        db.merge(org)
        config = OrgColumnConfig(
            org_id=org_data["id"],
            columns=json.dumps(org_data["columns"]),
        )
        db.merge(config)

        user = User(
            id=f"user-{org_data['id']}",
            org_id=org_data["id"],
            email=f"admin@{org_data['name'].lower().replace(' ', '')}.com",
        )
        db.merge(user)

    db.flush()
    print(f"Seeding {employee_count} employees...")
    batch_size = 1000
    for i in range(0, employee_count, batch_size):
        batch = []
        for j in range(batch_size):
            org_id = random.choice([o["id"] for o in ORGS])
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            idx = i + j
            emp = Employee(
                id=str(uuid.uuid4()),
                org_id=org_id,
                name=f"{first} {last}",
                email=f"{first.lower()}.{last.lower()}{idx}@example.com",
                phone=f"09{random.randint(10000000, 99999999)}",
                department=random.choice(DEPARTMENTS),
                location=random.choice(LOCATIONS),
                position=random.choice(POSITIONS),
            )
            batch.append(emp)
        db.bulk_save_objects(batch)
        db.flush()
        if (i // batch_size) % 10 == 0:
            print(f"  {i + batch_size:,} / {employee_count:,}")

    db.commit()
    print("Done.")
    import jwt as pyjwt
    for org_data in ORGS:
        token = pyjwt.encode(
            {"sub": f"user-{org_data['id']}", "org_id": org_data["id"], "exp": 9999999999},
            org_data["secret"],
            algorithm="HS256",
        )
        print(f"\n{org_data['name']} token:\n  {token}")


if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db=db)
