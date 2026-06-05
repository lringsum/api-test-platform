import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app import db  # noqa: E402
from app import models  # noqa: E402,F401


COPY_ORDER = [
    "projects",
    "prompt_templates",
    "modules",
    "environments",
    "variables",
    "testcases",
    "scenarios",
    "scenario_steps",
    "executions",
    "execution_details",
    "reports",
    "scenario_executions",
    "scenario_execution_details",
]


def normalize_database_url(url):
    if not url:
        return url
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


def default_source_url():
    return "sqlite:///" + str(PROJECT_ROOT / "instance" / "app.db")


def build_source_url(raw_url):
    if raw_url:
        return normalize_database_url(raw_url)
    return default_source_url()


def build_target_url(raw_url):
    if not raw_url:
        raise ValueError("Missing target PostgreSQL URL. Set DATABASE_URL or --target.")
    return normalize_database_url(raw_url)


def copy_table(source_conn, target_conn, table_name):
    table = db.metadata.tables[table_name]
    rows = source_conn.execute(table.select()).mappings().all()
    if not rows:
        print(f"[skip] {table_name}: no rows")
        return

    payload = [dict(row) for row in rows]
    target_conn.execute(table.insert(), payload)
    print(f"[copy] {table_name}: {len(payload)} rows")


def reset_postgres_sequences(target_conn):
    dialect_name = target_conn.dialect.name
    if dialect_name != "postgresql":
        return

    for table_name in COPY_ORDER:
        table = db.metadata.tables[table_name]
        if "id" not in table.c:
            continue

        max_id = target_conn.execute(text(f'SELECT COALESCE(MAX(id), 0) FROM "{table_name}"')).scalar_one()
        seq_name = target_conn.execute(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": table_name, "column_name": "id"},
        ).scalar_one()
        if seq_name:
            target_conn.execute(
                text("SELECT setval(CAST(:seq_name AS regclass), :seq_value, :is_called)"),
                {
                    "seq_name": seq_name,
                    "seq_value": max_id if max_id > 0 else 1,
                    "is_called": max_id > 0,
                },
            )


def main():
    parser = argparse.ArgumentParser(description="Copy data from SQLite to PostgreSQL.")
    parser.add_argument(
        "--source",
        default=os.environ.get("SOURCE_DATABASE_URL"),
        help="Source database URL. Defaults to ./instance/app.db",
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("TARGET_DATABASE_URL") or os.environ.get("DATABASE_URL"),
        help="Target PostgreSQL URL. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the copy plan without writing any data.",
    )
    args = parser.parse_args()

    source_url = build_source_url(args.source)
    target_url = build_target_url(args.target)

    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url)

    print(f"Source: {source_url}")
    print(f"Target: {target_url}")
    print("Creating target tables if needed...")
    db.metadata.create_all(target_engine)

    if args.dry_run:
        with source_engine.connect() as source_conn:
            for table_name in COPY_ORDER:
                table = db.metadata.tables[table_name]
                count = source_conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one()
                print(f"[dry-run] {table_name}: {count} rows")
        return

    with source_engine.connect() as source_conn, target_engine.begin() as target_conn:
        for table_name in COPY_ORDER:
            copy_table(source_conn, target_conn, table_name)
        reset_postgres_sequences(target_conn)

    print("Migration completed successfully.")


if __name__ == "__main__":
    main()
