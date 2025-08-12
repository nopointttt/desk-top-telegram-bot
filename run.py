# Файл: C:\desk_top\run.py
import asyncio
import logging
from src.bot import main
from src.db.session import init_db

async def start():
    """Функция запуска, включающая инициализацию БД."""
    await init_db()
    await main()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start())