# Файл: C:\desk_top\src\handlers\session.py
import logging
import json
import asyncio
from aiogram import Router, F, Bot
from aiogram.enums import ChatAction
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.repository import UserRepository, SessionRepository, PersonalizedPromptRepository
from src.services.llm_client import LLMClient
from src.services.rag_client import RAGClient

router = Router()
# ... (код до handle_text_message без изменений)
profile_choice_keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Кодер"), KeyboardButton(text="Продакт менеджер")], [KeyboardButton(text="Личный ассистент")]], resize_keyboard=True, one_time_keyboard=True)
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
    await message.answer(f"Новая сессия #{new_db_session.id} с профилем '{message.text}' начата. Что будем делать?")

# --- ОБНОВЛЕННЫЙ ОБРАБОТЧИК ---
@router.message()
async def handle_text_message(message: Message, session: AsyncSession, bot: Bot, llm_client: LLMClient, rag_client: RAGClient):
    user_id = message.from_user.id
    session_repo = SessionRepository(session)
    active_session = await session_repo.get_active_session(user_id)
    if not active_session:
        await message.answer("Нет активной сессии. Начните с /start_session")
        return

    status_message = await message.answer("Думаю... 🤔")
    log_text = "Думаю... 🤔"
    try:
        prompt_repo = PersonalizedPromptRepository(session)
        system_prompt = await prompt_repo.get_prompt(user_id, active_session.active_profile)
        if not system_prompt:
            await status_message.edit_text("Профиль не настроен. Начните с /personalize")
            return
        
        # --- НАЧАЛО ИСПРАВЛЕНИЯ: Защита от пустой истории ---
        history_str = active_session.message_history or '[]'
        history = json.loads(history_str)
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

        await asyncio.sleep(0.5)
        log_text += "\n`-> Ищу релевантную информацию в памяти...`"
        await status_message.edit_text(log_text, parse_mode="Markdown")
        
        relevant_summaries = await rag_client.find_relevant_summaries(user_id, message.text)
        
        await asyncio.sleep(0.5)
        log_text += f"\n`-> Найдено релевантных итогов: {len(relevant_summaries)}`"
        log_text += "\n`-> Формирую запрос к AI...`"
        await status_message.edit_text(log_text, parse_mode="Markdown")

        response_text = await llm_client.get_response(
            system_prompt, history, message.text, rag_context=relevant_summaries
        )

        current_history_text = " ".join([msg['content'] for msg in history])
        token_count = llm_client.count_tokens(current_history_text)
        CONTEXT_WINDOW = 16000 
        response_with_context = (
            f"{response_text}\n\n"
            f"--- \n"
            f"*Контекст сессии: {token_count} / {CONTEXT_WINDOW} токенов*"
        )
        
        await status_message.edit_text(response_with_context, parse_mode="Markdown")
        await session_repo.update_message_history(active_session.id, {"role": "user", "content": message.text})
        await session_repo.update_message_history(active_session.id, {"role": "assistant", "content": response_text})
    except Exception as e:
        logging.error(f"Error in handle_text_message: {e}")
        await status_message.edit_text("Произошла непредвиденная ошибка.")

@router.message(Command("end_session"))
async def cmd_end_session(message: Message, session: AsyncSession, llm_client: LLMClient, rag_client: RAGClient):
    repo = SessionRepository(session)
    active_session = await repo.get_active_session(message.from_user.id)
    if not active_session:
        await message.answer("У вас нет активных сессий.")
        return
    await message.answer("Подвожу итоги сессии...")
    # --- НАЧАЛО ИСПРАВЛЕНИЯ: Защита от пустой истории ---
    history_str = active_session.message_history or '[]'
    history = json.loads(history_str)
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
    if history:
        summary = await llm_client.get_summary(history)
        await rag_client.save_summary(active_session.id, message.from_user.id, summary)
    
    await repo.close_all_active_sessions(message.from_user.id)
    await message.answer(f"Сессия #{active_session.id} завершена. Итоги сохранены.")

# ... (остальной код без изменений) ...
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