# Файл: C:\desk_top\migrate_db.py
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path, чтобы импортировать src.config
root_dir = Path(__file__).parent
sys.path.append(str(root_dir))

from sqlalchemy.ext.asyncio import create_async_engine
from src.config import DATABASE_URL

SQL = r"""
-- Создание таблицы modes (если ее нет)
CREATE TABLE IF NOT EXISTS modes (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    name VARCHAR NOT NULL,
    system_prompt TEXT,
    tools_config TEXT,
    temperature VARCHAR,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_mode_project_name UNIQUE (project_id, name)
);

-- Индексы по modes
CREATE INDEX IF NOT EXISTS ix_modes_id ON modes (id);
CREATE INDEX IF NOT EXISTS ix_modes_project_id ON modes (project_id);

-- Идемпотентные ALTER для случаев, когда modes уже существовала без колонок
ALTER TABLE modes ADD COLUMN IF NOT EXISTS tools_config TEXT;
ALTER TABLE modes ADD COLUMN IF NOT EXISTS temperature VARCHAR;

-- Привязка сессии к модам
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS mode_id INTEGER NULL REFERENCES modes(id);
CREATE INDEX IF NOT EXISTS ix_sessions_mode_id ON sessions (mode_id);

-- Контекстный режим в сессии
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS context_mode VARCHAR;
UPDATE sessions SET context_mode = 'project' WHERE context_mode IS NULL;
ALTER TABLE sessions ALTER COLUMN context_mode SET NOT NULL;
ALTER TABLE sessions ALTER COLUMN context_mode SET DEFAULT 'project';
"""

async def main():
    if not DATABASE_URL or "None" in str(DATABASE_URL):
        print("ERROR: DATABASE_URL is not configured. Check your .env and src/config.py")
        return
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(SQL)
    await engine.dispose()
    print("Migration completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())
