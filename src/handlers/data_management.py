# Файл: src/handlers/data_management.py
import json
import logging # <-- Добавьте импорт
from aiogram import Router, Bot, F # <-- Добавьте F
from aiogram.types import Message, BufferedInputFile, ReplyKeyboardRemove # <-- Добавьте ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext # <-- Добавьте FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.repository import UserRepository, SessionRepository, PersonalizedPromptRepository
from src.personalization.states import DataManagement # <-- Добавьте импорт
from src.personalization.keyboards import confirm_deletion_keyboard # <-- Добавьте импорт

router = Router()

@router.message(Command("export_data"))
async def cmd_export_data(message: Message, session: AsyncSession):
    """
    Собирает все данные пользователя и отправляет их в виде JSON-файла.
    """
    user_id = message.from_user.id
    await message.answer("Собираю ваши данные... Это может занять некоторое время.")

    # 1. Инициализируем репозитории
    user_repo = UserRepository(session)
    session_repo = SessionRepository(session)
    prompt_repo = PersonalizedPromptRepository(session)

    # 2. Получаем все данные пользователя
    user_data = await user_repo.get_or_create_user(telegram_id=user_id)
    user_sessions = await session_repo.list_sessions(user_id)
    
    # Предполагаем, что профили хранятся под известными именами
    profiles = ["coder", "product_manager", "personal_assistant"]
    user_prompts = []
    for profile in profiles:
        prompt = await prompt_repo.get_prompt(user_id, profile)
        if prompt:
            user_prompts.append({"profile": profile, "prompt_text": prompt})

    # 3. Формируем структуру для JSON-файла
    export_payload = {
        "user_info": {
            "telegram_id": user_data.telegram_id,
            "username": user_data.username,
            "created_at": user_data.created_at.isoformat() if user_data.created_at else None,
        },
        "sessions": [
            {
                "id": s.id,
                "status": s.status,
                "active_profile": s.active_profile,
                "message_history": s.message_history, # Уже является списком
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            }
            for s in user_sessions
        ],
        "personalized_prompts": user_prompts,
    }

    # 4. Преобразуем в JSON и отправляем файл
    json_data = json.dumps(export_payload, indent=4, ensure_ascii=False).encode('utf-8')
    
    input_file = BufferedInputFile(
        file=json_data,
        filename=f"export_user_{user_id}.json"
    )

    await message.answer_document(
        document=input_file,
        caption="Ваши данные готовы. Сохраните этот файл."
    )
# --- НОВЫЙ КОД ---
@router.message(Command("delete_my_data"))
async def cmd_delete_my_data(message: Message, state: FSMContext):
    """
    Запрашивает подтверждение на удаление всех данных пользователя.
    """
    await state.set_state(DataManagement.confirming_deletion)
    await message.answer(
        "<b>ВНИМАНИЕ!</b> Это действие безвозвратно удалит всю вашу информацию: "
        "профиль, все сессии и персональные настройки.\n\n"
        "Вы уверены, что хотите продолжить?",
        reply_markup=confirm_deletion_keyboard,
        parse_mode="HTML"
    )

@router.message(DataManagement.confirming_deletion, F.text == "Да, удалить все мои данные")
async def process_confirm_deletion(message: Message, state: FSMContext, session: AsyncSession):
    """
    Обрабатывает подтверждение и удаляет данные.
    """
    await state.clear()
    user_repo = UserRepository(session)
    await user_repo.delete_all_user_data(message.from_user.id)

    await message.answer(
        "Все ваши данные были успешно удалены. Спасибо за использование.",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(DataManagement.confirming_deletion, F.text == "Отмена")
async def process_cancel_deletion(message: Message, state: FSMContext):
    """
    Обрабатывает отмену удаления.
    """
    await state.clear()
    await message.answer(
        "Действие отменено. Ваши данные в безопасности.",
        reply_markup=ReplyKeyboardRemove()
    )
# --- КОНЕЦ НОВОГО КОДА ---