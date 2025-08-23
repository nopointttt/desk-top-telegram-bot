"""
Файл: C:\desk_top\check_db.py
Назначение: Быстрый smoke-check соединения и схемы БД (PostgreSQL).

Проверяет:
- наличие таблицы modes и её ключевых колонок/уникальности
- наличие колонок sessions.mode_id и sessions.context_mode (NOT NULL, DEFAULT 'project')
- наличие ключевых индексов
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в пути, чтобы найти src.config
root_dir = Path(__file__).parent
sys.path.append(str(root_dir))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from src.config import DATABASE_URL


def _print_ok(msg: str):
    print(f"[ OK ] {msg}")


def _print_warn(msg: str):
    print(f"[WARN] {msg}")


def _print_err(msg: str):
    print(f"[FAIL] {msg}")


async def check_connection_and_schema():
    print("--- Database Smoke-Check ---")
    if not DATABASE_URL or "None" in str(DATABASE_URL):
        _print_err("Database URL is not configured correctly in .env file (src/config.py).")
        return

    # Маскируем URL для печати
    try:
        user_part, host_part = str(DATABASE_URL).split('@')
        user, _ = user_part.split('//')[1].split(':')
        masked_url = f"{user}@{host_part}"
        print(f"Target: {masked_url}")
    except Exception:
        print("Target: <unparsed DATABASE_URL>")

    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            _print_ok("Connected to DB")

            # 1) Таблица modes
            res = await conn.execute(text("SELECT to_regclass('public.modes') IS NOT NULL"))
            modes_exists = bool(res.scalar_one())
            if modes_exists:
                _print_ok("Table 'modes' exists")
            else:
                _print_err("Table 'modes' missing. Run migrate_db.py")

            if modes_exists:
                # Проверим ключевые колонки в modes
                need_cols = {"id", "project_id", "name", "system_prompt", "tools_config", "temperature", "created_at"}
                res = await conn.execute(text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'modes'
                    """
                ))
                cols = {r[0] for r in res.fetchall()}
                missing = sorted(list(need_cols - cols))
                if missing:
                    _print_err(f"'modes' missing columns: {', '.join(missing)}")
                else:
                    _print_ok("'modes' columns present")

                # Уникальное ограничение uq_mode_project_name
                res = await conn.execute(text(
                    """
                    SELECT COUNT(*) FROM pg_constraint
                    WHERE conname = 'uq_mode_project_name'
                    """
                ))
                if res.scalar_one() == 1:
                    _print_ok("Constraint 'uq_mode_project_name' exists")
                else:
                    _print_err("Constraint 'uq_mode_project_name' missing")

                # Индексы по modes
                for idx in ("ix_modes_id", "ix_modes_project_id"):
                    res = await conn.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": f"public.{idx}"})
                    if bool(res.scalar_one()):
                        _print_ok(f"Index '{idx}' exists")
                    else:
                        _print_warn(f"Index '{idx}' missing")

            # 2) Колонки в sessions: mode_id, context_mode
            res = await conn.execute(text("SELECT to_regclass('public.sessions') IS NOT NULL"))
            sessions_exists = bool(res.scalar_one())
            if not sessions_exists:
                _print_err("Table 'sessions' missing")
            else:
                _print_ok("Table 'sessions' exists")

                # mode_id column + index
                res = await conn.execute(text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'sessions' AND column_name = 'mode_id'
                    """
                ))
                if res.fetchone():
                    _print_ok("Column sessions.mode_id exists")
                else:
                    _print_err("Column sessions.mode_id missing")

                res = await conn.execute(text("SELECT to_regclass('public.ix_sessions_mode_id') IS NOT NULL"))
                if bool(res.scalar_one()):
                    _print_ok("Index 'ix_sessions_mode_id' exists")
                else:
                    _print_warn("Index 'ix_sessions_mode_id' missing")

                # context_mode column (NOT NULL, DEFAULT 'project')
                res = await conn.execute(text(
                    """
                    SELECT is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='sessions' AND column_name='context_mode'
                    """
                ))
                row = res.fetchone()
                if not row:
                    _print_err("Column sessions.context_mode missing")
                else:
                    is_nullable, column_default = row
                    if is_nullable == 'NO':
                        _print_ok("sessions.context_mode is NOT NULL")
                    else:
                        _print_err("sessions.context_mode should be NOT NULL")
                    # default может иметь вид ''project'::character varying
                    if column_default and "'project'" in column_default:
                        _print_ok("sessions.context_mode has DEFAULT 'project'")
                    else:
                        _print_warn("sessions.context_mode DEFAULT 'project' not detected")

    except Exception as e:
        _print_err("Failed to connect or query the database")
        print("-------")
        print(f"Details: {e}")
        print("-------")
        print("Hints: check PostgreSQL service, .env credentials, network access")
    finally:
        await engine.dispose()
        print("\n--- Smoke-Check Finished ---")


if __name__ == "__main__":
    asyncio.run(check_connection_and_schema())