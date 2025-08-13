# Файл: C:\desk_top\run.py
import asyncio
import logging
import sys
from pathlib import Path

root_dir = Path(__file__).parent
sys.path.append(str(root_dir))

from src.bot import main
from src.db.session import db_init

async def start():
    """Функция запуска, включающая инициализацию БД."""
    await db_init()
    await main()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start())