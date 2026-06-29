"""Create the normalized enterprise tables.

Usage (run from Backend/):
    # 1) Create the tables in whatever DATABASE_URL points at (Supabase/Postgres
    #    or the local sqlite default):
    python -m scripts.init_db

    # 2) Or just PRINT the PostgreSQL DDL to paste into the Supabase SQL Editor
    #    (no connection made):
    python -m scripts.init_db --print-sql
"""
from __future__ import annotations

import sys


def print_sql() -> None:
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex, CreateTable

    from app.db.models import Base

    dialect = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        print(str(CreateTable(table).compile(dialect=dialect)).strip() + ";\n")
        for idx in table.indexes:
            print(str(CreateIndex(idx).compile(dialect=dialect)).strip() + ";")
        print()


def create() -> None:
    from app.config import get_settings
    from app.db.models import Base
    from app.db.session import get_engine, init_db

    url = get_settings().database_url
    print(f"Connecting to: {url.split('://', 1)[0]}://…")
    init_db()
    get_engine()  # ensure engine
    print(f"Created/verified {len(Base.metadata.tables)} tables:")
    for name in Base.metadata.tables:
        print(f"  - {name}")


if __name__ == "__main__":
    if "--print-sql" in sys.argv:
        print_sql()
    else:
        create()
