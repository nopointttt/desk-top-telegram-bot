# Файл: C:\desk_top\src\bot.py
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import TELEGRAM_TOKEN
from src.handlers import general, session as session_handlers, personalization
from src.db.session import db
from src.services.llm_client import LLMClient
from src.services.rag_client import RAGClient

# Middleware для передачи сессии БД в обработчики
async def db_session_middleware(handler, event: Update, data: dict):
    async with db.AsyncSessionLocal() as session:
        data['session'] = session
        return await handler(event, data)

async def main():
    """Основная функция для запуска бота."""
    bot = Bot(token=TELEGRAM_TOKEN)
    
    # --- НАЧАЛО ИСПРАВЛЕНИЯ ---
    # Создаем клиентов один раз при запуске
    llm_client = LLMClient()
    rag_client = RAGClient()
    await rag_client.initialize() # Инициализируем RAG-клиент и индекс

    # Передаем созданные клиенты в Dispatcher, чтобы они были доступны во всех хендлерах
    dp = Dispatcher(llm_client=llm_client, rag_client=rag_client)
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    dp.update.middleware(db_session_middleware)

    dp.include_router(general.router)
    dp.include_router(personalization.router)
    dp.include_router(session_handlers.router)

    logging.info("Starting bot...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logging.info("Bot stopped.")