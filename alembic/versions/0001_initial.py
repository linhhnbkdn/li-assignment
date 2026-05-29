"""initial

Revision ID: 0001
Revises:
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("secret", sa.String(), nullable=False),
    )
    op.create_table(
        "org_column_configs",
        sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("columns", sa.String(), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email", sa.String(), nullable=False, unique=True),
    )
    op.create_table(
        "employees",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String()),
        sa.Column("phone", sa.String()),
        sa.Column("department", sa.String()),
        sa.Column("location", sa.String()),
        sa.Column("position", sa.String()),
    )
    op.create_index("ix_emp_org", "employees", ["org_id"])
    op.create_index("ix_emp_org_dept", "employees", ["org_id", "department"])
    op.create_index("ix_emp_org_loc", "employees", ["org_id", "location"])
    op.create_index("ix_emp_org_pos", "employees", ["org_id", "position"])

    op.execute("""
        CREATE VIRTUAL TABLE employees_fts USING fts5(
            name, email,
            content=employees,
            content_rowid=rowid
        )
    """)
    op.execute("""
        CREATE TRIGGER employees_ai AFTER INSERT ON employees BEGIN
            INSERT INTO employees_fts(rowid, name, email)
            VALUES (new.rowid, new.name, new.email);
        END
    """)
    op.execute("""
        CREATE TRIGGER employees_ad AFTER DELETE ON employees BEGIN
            INSERT INTO employees_fts(employees_fts, rowid, name, email)
            VALUES ('delete', old.rowid, old.name, old.email);
        END
    """)
    op.execute("""
        CREATE TRIGGER employees_au AFTER UPDATE ON employees BEGIN
            INSERT INTO employees_fts(employees_fts, rowid, name, email)
            VALUES ('delete', old.rowid, old.name, old.email);
            INSERT INTO employees_fts(rowid, name, email)
            VALUES (new.rowid, new.name, new.email);
        END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS employees_au")
    op.execute("DROP TRIGGER IF EXISTS employees_ad")
    op.execute("DROP TRIGGER IF EXISTS employees_ai")
    op.execute("DROP TABLE IF EXISTS employees_fts")
    op.drop_table("employees")
    op.drop_table("users")
    op.drop_table("org_column_configs")
    op.drop_table("organizations")
