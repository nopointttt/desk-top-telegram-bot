# Файл: C:\desk_top\src\bot.py
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import Update, BotCommand
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import TELEGRAM_TOKEN
from src.handlers import general, session as session_handlers, personalization, data_management
from src.db.session import db
from src.db.repository import SessionRepository
from src.services.llm_client import LLMClient
from src.services.rag_client import RAGClient

async def db_session_middleware(handler, event: Update, data: dict):
    async with db.AsyncSessionLocal() as session:
        data['session'] = session
        return await handler(event, data)

async def scheduled_cleanup(session_maker):
    async with session_maker() as session:
        repo = SessionRepository(session)
        await repo.delete_old_sessions()

# --- НОВЫЙ КОД: Функция для установки меню команд ---
async def set_main_menu(bot: Bot):
    """
    Создает и устанавливает основное меню команд бота.
    """
    main_menu_commands = [
        BotCommand(command='/start', description='▶️ Запустить/перезапустить бота'),
        BotCommand(command='/personalize', description='👤 Настроить профиль агента'),
        BotCommand(command='/start_session', description='🚀 Начать новую сессию'),
        BotCommand(command='/end_session', description='🛑 Завершить текущую сессию'),
        BotCommand(command='/list_sessions', description='📋 Показать историю сессий'),
        BotCommand(command='/export_data', description='📥 Скачать свои данные'),
        BotCommand(command='/delete_my_data', description='🗑️ Удалить все свои данные')
    ]
    await bot.set_my_commands(main_menu_commands)
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
    dp.include_router(data_management.router)
    dp.include_router(session_handlers.router)

    # --- НОВЫЙ КОД: Вызов функции установки меню ---
    await set_main_menu(bot)
    # --- КОНЕЦ НОВОГО КОДА ---

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(scheduled_cleanup, trigger='interval', days=1, kwargs={'session_maker': db.AsyncSessionLocal})
    scheduler.start()

    logging.info("Starting bot...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logging.info("Bot stopped.")