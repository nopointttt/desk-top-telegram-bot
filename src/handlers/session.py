# Файл: C:\desk_top\src\handlers\session.py
import logging
import json
import asyncio
from aiogram import Router, F, Bot
from aiogram.enums import ChatAction
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.repository import UserRepository, SessionRepository, PersonalizedPromptRepository
from src.services.llm_client import LLMClient
from src.services.rag_client import RAGClient

router = Router()
logger = logging.getLogger(__name__)

profile_choice_keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Кодер"), KeyboardButton(text="Продакт менеджер")], [KeyboardButton(text="Личный ассистент")]], resize_keyboard=True, one_time_keyboard=True)

# --- ОБРАБОТЧИКИ КОМАНД И КОНКРЕТНЫХ ДЕЙСТВИЙ ---

@router.message(Command("start_session"))
async def cmd_start_session(message: Message):
    await message.answer("С каким профилем начать сессию?", reply_markup=profile_choice_keyboard)

@router.message(F.text.in_({"Кодер", "Продакт менеджер", "Личный ассистент"}))
async def process_profile_choice(message: Message, session: AsyncSession):
    profile_map = { "Кодер": "coder", "Продакт менеджер": "product_manager", "Личный ассистент": "personal_assistant" }
    profile = profile_map.get(message.text)
    user_repo = UserRepository(session)
    session_repo = SessionRepository(session)
    user = await user_repo.get_or_create_user(telegram_id=message.from_user.id, username=message.from_user.username)
    new_db_session = await session_repo.start_new_session(user, profile)
    logger.info(f"ANALYTICS - Event: SessionStarted, UserID: {message.from_user.id}, Details: {{'session_id': {new_db_session.id}, 'profile': '{profile}'}}")
    await message.answer(f"Новая сессия #{new_db_session.id} с профилем '{message.text}' начата. Что будем делать?", reply_markup=ReplyKeyboardRemove())

@router.message(Command("end_session"))
async def cmd_end_session(message: Message, session: AsyncSession, llm_client: LLMClient, rag_client: RAGClient):
    repo = SessionRepository(session)
    active_session = await repo.get_active_session(message.from_user.id)
    if not active_session:
        await message.answer("У вас нет активных сессий.")
        return
    await message.answer("Подвожу итоги сессии...")
    history = active_session.message_history
    if history:
        summary = await llm_client.get_summary(history)
        await rag_client.save_summary(active_session.id, message.from_user.id, summary)
    logger.info(f"ANALYTICS - Event: SessionEnded, UserID: {message.from_user.id}, Details: {{'session_id': {active_session.id}}}")
    await repo.close_all_active_sessions(message.from_user.id)
    await message.answer(f"Сессия #{active_session.id} завершена. Итоги сохранены.")

@router.message(Command("list_sessions"))
async def cmd_list_sessions(message: Message, session: AsyncSession):
    repo = SessionRepository(session)
    user_sessions = await repo.list_sessions(message.from_user.id)
    if not user_sessions:
        await message.answer("У вас еще нет ни одной сессии.")
        return
    response_text = "Ваши сессии:\n\n"
    for s in user_sessions:
        status_emoji = "🟢" if s.status == 'active' else "🔴"
        response_text += f"{status_emoji} Сессия #{s.id} от {s.created_at.strftime('%Y-%m-%d %H:%M')}\n"
    await message.answer(response_text)

# --- ОБЩИЙ ОБРАБОТЧИК ТЕКСТА (С УЛУЧШЕННЫМ UX) ---

@router.message(F.content_type.in_({'text'}))
async def handle_text_message(message: Message, session: AsyncSession, bot: Bot, llm_client: LLMClient, rag_client: RAGClient):
    user_id = message.from_user.id
    user_repo = UserRepository(session)
    session_repo = SessionRepository(session)
    
    user = await user_repo.get_or_create_user(user_id, message.from_user.username)
    request_tokens = llm_client.count_tokens(message.text)
    if not await user_repo.check_and_update_limits(user, request_tokens):
        await message.answer("Вы превысили суточный лимит использования токенов. Попробуйте снова завтра.")
        return

    active_session = await session_repo.get_active_session(user_id)
    if not active_session:
        await message.answer("Нет активной сессии. Начните с /start_session")
        return

    # --- УЛУЧШЕННЫЙ UX ---
    status_message = await message.answer("<i>Анализирую запрос...</i>")
    try:
        prompt_repo = PersonalizedPromptRepository(session)
        system_prompt = await prompt_repo.get_prompt(user_id, active_session.active_profile)
        if not system_prompt:
            await status_message.edit_text("Профиль не настроен. Начните с /personalize")
            return
        
        history = active_session.message_history

        # Этап 1: Поиск в RAG
        await status_message.edit_text("<i>Анализирую запрос...\nИщу релевантную информацию в долгосрочной памяти...</i>")
        relevant_summaries = await rag_client.find_relevant_summaries(user_id, message.text)
        
        # Этап 2: Формирование запроса к LLM
        log_text = (
            f"<i>Анализирую запрос...\n"
            f"Ищу релевантную информацию в долгосрочной памяти... ✓\n"
            f"Найдено {len(relevant_summaries)} релевантных итогов.\n"
            f"Формирую запрос к AI...</i>"
        )
        await status_message.edit_text(log_text)

        response_text = await llm_client.get_response(
            system_prompt, history, message.text, rag_context=relevant_summaries
        )

        response_tokens = llm_client.count_tokens(response_text)
        await user_repo.check_and_update_limits(user, response_tokens)

        current_history_text = " ".join([msg['content'] for msg in history])
        token_count = llm_client.count_tokens(current_history_text)
        CONTEXT_WINDOW = 16000 
        response_with_context = (
            f"{response_text}\n\n"
            f"--- \n"
            f"<i>Контекст сессии: {token_count} / {CONTEXT_WINDOW} токенов</i>"
        )
        
        # Этап 3: Финальный ответ
        await status_message.edit_text(response_with_context)
        
        await session_repo.update_message_history(active_session.id, {"role": "user", "content": message.text})
        await session_repo.update_message_history(active_session.id, {"role": "assistant", "content": response_text})
    except Exception as e:
        logger.error(f"Error in handle_text_message: {e}", exc_info=True)
        await status_message.edit_text("Произошла непредвиденная ошибка.")