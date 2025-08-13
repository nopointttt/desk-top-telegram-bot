# Файл: C:\desk_top\run.py
import asyncio
import logging
import sys
from pathlib import Path

# --- НАЧАЛО ИСПРАВЛЕНИЯ ---
# Добавляем корневую папку проекта в системные пути
# Это гарантирует, что Python всегда знает, где искать папку `src`
root_dir = Path(__file__).parent
sys.path.append(str(root_dir))
# --- КОНЕЦ ИСПРАВЛЕНИЯ ---

from src.bot import main
from src.db.session import init_db

async def start():
    """Функция запуска, включающая инициализацию БД."""
    await init_db()
    await main()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start())