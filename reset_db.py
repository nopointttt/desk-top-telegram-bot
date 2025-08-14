# Файл: C:\desk_top\reset_db.py
import asyncio
import sys
from pathlib import Path

print("--- [DB RESET SCRIPT]: Starting ---")

root_dir = Path(__file__).parent
sys.path.append(str(root_dir))

from src.db.models import Base
from src.db.session import db_init, db

async def drop_tables():
    """Подключается к БД и удаляет все таблицы, определенные в Base.metadata."""
    print("--- [DB RESET SCRIPT]: Initializing DB connection...")
    await db_init()
    
    print("--- [DB RESET SCRIPT]: Dropping all tables...")
    async with db.engine.begin() as conn:
        # Удаляем таблицы в обратном порядке их создания
        await conn.run_sync(Base.metadata.drop_all)
    
    print("--- [DB RESET SCRIPT]: Tables dropped successfully. ---")
    print("--- [DB RESET SCRIPT]: Finished ---")

if __name__ == "__main__":
    # Запускаем асинхронную функцию
    asyncio.run(drop_tables())