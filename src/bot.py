# Файл: C:\desk_top\src\bot.py
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import TELEGRAM_TOKEN
from src.handlers import general, session as session_handlers, personalization
from src.db.session import db
from src.db.repository import SessionRepository
from src.services.llm_client import LLMClient
from src.services.rag_client import RAGClient

async def db_session_middleware(handler, event: Update, data: dict):
    async with db.AsyncSessionLocal() as session:
        data['session'] = session
        return await handler(event, data)

# --- НАЧАЛО НОВОГО КОДА ---
async def scheduled_cleanup(session_maker):
    """Функция, которую будет вызывать планировщик."""
    async with session_maker() as session:
        repo = SessionRepository(session)
        await repo.delete_old_sessions()
# --- КОНЕЦ НОВОГО КОДА ---

async def main():
    bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    
    llm_client = LLMClient()
    rag_client = RAGClient()
    await rag_client.initialize()
    dp = Dispatcher(llm_client=llm_client, rag_client=rag_client)

    dp.update.middleware(db_session_middleware)
    
    dp.include_router(general.router)
    dp.include_router(personalization.router)
    dp.include_router(session_handlers.router)

    # --- НАЧАЛО НОВОГО КОДА ---
    # Настройка и запуск планировщика
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(scheduled_cleanup, trigger='interval', days=1, kwargs={'session_maker': db.AsyncSessionLocal})
    scheduler.start()
    # --- КОНЕЦ НОВОГО КОДА ---

    logging.info("Starting bot...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logging.info("Bot stopped.")