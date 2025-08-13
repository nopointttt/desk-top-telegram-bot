# Файл: C:\desk_top\src\handlers\session.py
import logging
import json
from aiogram import Router, F, Bot
from aiogram.enums import ChatAction # <-- ИЗМЕНЕНИЕ 1: Импортируем ChatAction
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.repository import UserRepository, SessionRepository, PersonalizedPromptRepository
from src.services.llm_client import LLMClient

router = Router()

# ... (клавиатура и обработчики /start_session, выбора профиля остаются без изменений)
profile_choice_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Кодер"), KeyboardButton(text="Продакт менеджер")],
        [KeyboardButton(text="Личный ассистент")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

@router.message(Command("start_session"))
async def cmd_start_session(message: Message, session: AsyncSession):
    # ...
    await message.answer("С каким профилем начать сессию?", reply_markup=profile_choice_keyboard)

@router.message(F.text.in_({"Кодер", "Продакт менеджер", "Личный ассистент"}))
async def process_profile_choice(message: Message, session: AsyncSession):
    # ...
    profile_map = { "Кодер": "coder", "Продакт менеджер": "product_manager", "Личный ассистент": "personal_assistant" }
    profile = profile_map.get(message.text)
    user_repo = UserRepository(session)
    session_repo = SessionRepository(session)
    user = await user_repo.get_or_create_user(telegram_id=message.from_user.id, username=message.from_user.username)
    new_db_session = await session_repo.start_new_session(user, profile)
    await message.answer(f"Новая сессия #{new_db_session.id} с профилем '{message.text}' начата. Что будем делать?")

# --- ОБНОВЛЕННЫЙ ОБРАБОТЧИК ДЛЯ ВСЕХ ТЕКСТОВЫХ СООБЩЕНИЙ ---
@router.message()
async def handle_text_message(message: Message, session: AsyncSession, bot: Bot): # <-- ИЗМЕНЕНИЕ 2: Добавляем 'bot'
    user_id = message.from_user.id
    session_repo = SessionRepository(session)
    active_session = await session_repo.get_active_session(user_id)

    if not active_session:
        await message.answer("У вас нет активной сессии. Начните новую с помощью /start_session")
        return

    # --- ИЗМЕНЕНИЕ 3: Немедленно показываем статус "печатает..." ---
    await bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)

    prompt_repo = PersonalizedPromptRepository(session)
    system_prompt = await prompt_repo.get_prompt(user_id, active_session.active_profile)
    if not system_prompt:
        await message.answer("Профиль не настроен. Пожалуйста, настройте его с помощью /personalize")
        return

    history = json.loads(active_session.message_history)
    
    llm_client = LLMClient()
    response_text = await llm_client.get_response(system_prompt, history, message.text)
    
    await message.answer(response_text)

    await session_repo.update_message_history(active_session.id, {"role": "user", "content": message.text})
    await session_repo.update_message_history(active_session.id, {"role": "assistant", "content": response_text})

# ... (обработчики /end_session и /list_sessions остаются без изменений)
@router.message(Command("end_session"))
# ...
async def cmd_end_session(message: Message, session: AsyncSession):
    logging.info(f"User {message.from_user.id} ending session.")
    repo = SessionRepository(session)
    active_session = await repo.get_active_session(message.from_user.id)
    if not active_session:
        await message.answer("У вас нет активных сессий, чтобы завершать.")
        return
    await repo.close_all_active_sessions(message.from_user.id)
    await message.answer(f"Сессия #{active_session.id} завершена. Итоги сохранены в базу знаний.")

@router.message(Command("list_sessions"))
async def cmd_list_sessions(message: Message, session: AsyncSession):
    # ...
    logging.info(f"User {message.from_user.id} requesting session list.")
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