# Файл: C:\desk_top\src\bot.py
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import TELEGRAM_TOKEN
from src.handlers import general, session as session_handlers
from src.db.session import AsyncSessionLocal

# Middleware для передачи сессии БД в обработчики
async def db_session_middleware(handler, event: Update, data: dict):
    async with AsyncSessionLocal() as session:
        data['session'] = session
        return await handler(event, data)

async def main():
    """Основная функция для запуска бота."""
    bot = Bot(token=TELEGRAM_TOKEN)
    dp = Dispatcher()

    # Подключаем middleware
    dp.update.middleware(db_session_middleware)

    # Подключаем роутеры
    dp.include_router(general.router)
    dp.include_router(session_handlers.router)

    logging.info("Starting bot...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logging.info("Bot stopped.")