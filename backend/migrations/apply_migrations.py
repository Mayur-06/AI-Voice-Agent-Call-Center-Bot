import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from supabase import create_client
from app.config import settings


MIGRATIONS_DIR = Path(__file__).parent


def read_migration_file(filename: str) -> str:
    path = MIGRATIONS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Migration file not found: {path}")
    return path.read_text(encoding="utf-8")


async def apply_migration(sql: str, label: str):
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    try:
        response = supabase.postgrest.rpc("exec_sql", {"sql": sql}).execute()
        print(f"Applied: {label}")
    except Exception as exc:
        print(f"Migration RPC failed: {exc}")
        print("If your Supabase project does not have an exec_sql RPC, run the SQL in migrations/ via the Supabase Dashboard SQL Editor or Supabase CLI.")


async def main():
    if not settings.supabase_url or not settings.supabase_service_role_key:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment.")
        sys.exit(1)

    migration_file = "20240101_initial_schema.sql"
    sql = read_migration_file(migration_file)
    await apply_migration(sql, migration_file)
    print("Migrations complete.")


if __name__ == "__main__":
    asyncio.run(main())
