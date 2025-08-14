# Файл: C:\desk_top\src\handlers\personalization.py
import logging
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repository import PersonalizedPromptRepository
from src.personalization.states import Personalization
from src.personalization.keyboards import profile_keyboard

router = Router()
logger = logging.getLogger(__name__) # <-- Создаем логгер для модуля

@router.message(Command("personalize"))
async def cmd_personalize(message: Message, state: FSMContext):
    """Начинает процесс персонализации."""
    # --- АНАЛИТИКА ---
    logger.info(f"ANALYTICS - Event: PersonalizationStarted, UserID: {message.from_user.id}")
    # --- КОНЕЦ АНАЛИТИКИ ---
    
    await state.set_state(Personalization.choosing_profile)
    await message.answer(
        "Давайте настроим вашего агента. Выберите профиль:",
        reply_markup=profile_keyboard
    )

# --- Обработчики для профиля "Кодер" ---
@router.message(Personalization.choosing_profile, F.text == "Кодер")
async def start_coder_interview(message: Message, state: FSMContext):
    await state.set_state(Personalization.coder_interview_q1)
    await state.update_data(profile="coder")
    await message.answer(
        "Отлично! Ваш основной стек технологий (языки, фреймворки, БД)?",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(Personalization.coder_interview_q1)
async def process_coder_answer(message: Message, state: FSMContext, session: AsyncSession):
    user_data = await state.get_data()
    profile = user_data.get('profile', 'unknown')
    prompt_text = (
        "Ты — AI-ассистент для разработчика. Твоя главная задача — помогать с кодом, "
        f"отладкой и архитектурой. Всегда учитывай, что основной стек пользователя: {message.text}. "
        "Предоставляй примеры кода в этом стеке."
    )
    
    prompt_repo = PersonalizedPromptRepository(session)
    await prompt_repo.save_or_update_prompt(message.from_user.id, profile, prompt_text)
    
    # --- АНАЛИТИКА ---
    logger.info(f"ANALYTICS - Event: PersonalizationCompleted, UserID: {message.from_user.id}, Details: {{'profile': '{profile}'}}")
    # --- КОНЕЦ АНАЛИТИКИ ---

    await state.clear()
    await message.answer(f"Спасибо! Ваш профиль '{message.text}' настроен.")

# --- Обработчики для профиля "Продакт менеджер" ---
@router.message(Personalization.choosing_profile, F.text == "Продакт менеджер")
async def start_product_interview(message: Message, state: FSMContext):
    await state.set_state(Personalization.product_manager_interview_q1)
    await state.update_data(profile="product_manager")
    await message.answer(
        "Отлично! Опишите ваш продукт или сферу, в которой вы работаете, и ваши ключевые метрики.",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(Personalization.product_manager_interview_q1)
async def process_product_answer(message: Message, state: FSMContext, session: AsyncSession):
    user_data = await state.get_data()
    profile = user_data.get('profile', 'unknown')
    prompt_text = (
        "Ты — AI-ассистент для продакт-менеджера. Твоя задача — помогать с генерацией гипотез, "
        "анализом метрик и написанием user stories. "
        f"Всегда учитывай контекст продукта пользователя: {message.text}."
    )
    prompt_repo = PersonalizedPromptRepository(session)
    await prompt_repo.save_or_update_prompt(message.from_user.id, profile, prompt_text)

    # --- АНАЛИТИКА ---
    logger.info(f"ANALYTICS - Event: PersonalizationCompleted, UserID: {message.from_user.id}, Details: {{'profile': '{profile}'}}")
    # --- КОНЕЦ АНАЛИТИКИ ---

    await state.clear()
    await message.answer(f"Спасибо! Ваш профиль '{message.text}' настроен.")

# --- Обработчики для профиля "Личный ассистент" ---
@router.message(Personalization.choosing_profile, F.text == "Личный ассистент")
async def start_assistant_interview(message: Message, state: FSMContext):
    await state.set_state(Personalization.personal_assistant_interview_q1)
    await state.update_data(profile="personal_assistant")
    await message.answer(
        "Отлично! Опишите ваши основные рутинные задачи, которые вы хотели бы делегировать.",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(Personalization.personal_assistant_interview_q1)
async def process_assistant_answer(message: Message, state: FSMContext, session: AsyncSession):
    user_data = await state.get_data()
    profile = user_data.get('profile', 'unknown')
    prompt_text = (
        "Ты — персональный AI-ассистент. Твоя задача — помогать с организацией, "
        "планированием и написанием текстов. "
        f"Сфокусируйся на помощи в следующих задачах: {message.text}."
    )
    prompt_repo = PersonalizedPromptRepository(session)
    await prompt_repo.save_or_update_prompt(message.from_user.id, profile, prompt_text)
    
    # --- АНАЛИТИКА ---
    logger.info(f"ANALYTICS - Event: PersonalizationCompleted, UserID: {message.from_user.id}, Details: {{'profile': '{profile}'}}")
    # --- КОНЕЦ АНАЛИТИКИ ---

    await state.clear()
    await message.answer(f"Спасибо! Ваш профиль '{message.text}' настроен.")