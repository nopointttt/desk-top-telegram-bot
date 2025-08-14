# Файл: C:\desk_top\run.py
import asyncio
import logging
import sys
from pathlib import Path
import sentry_sdk  # Импорт остается

root_dir = Path(__file__).parent
sys.path.append(str(root_dir))

from src.bot import main
from src.db.session import db_init
from src.logging_config import setup_logging
from src.config import SENTRY_DSN

async def start():
    """Асинхронная функция запуска, которая теперь занимается только async-задачами."""
    await db_init()
    await main()

if __name__ == "__main__":
    # 1. Настраиваем логирование в первую очередь
    setup_logging()

    # 2. Инициализируем Sentry здесь, в синхронном контексте, ДО запуска asyncio
    if SENTRY_DSN:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
        )
        logging.info("Sentry initialized successfully.")
    else:
        logging.warning("SENTRY_DSN not found. Sentry is not initialized.")
    
    # 3. Запускаем асинхронный код
    try:
        asyncio.run(start())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")