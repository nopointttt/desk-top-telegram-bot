# Файл: C:\desk_top\src\handlers\context_mode.py
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repository import SessionRepository

router = Router()
logger = logging.getLogger(__name__)

VALID_MODES = {"project", "acl_mentions", "global"}

HELP_TEXT = (
    "Режимы контекста:\n"
    "- project — только текущий проект (по умолчанию)\n"
    "- acl_mentions — текущий проект + упоминания @[Project] с ACL-проверкой\n"
    "- global — весь контент пользователя без фильтра по проектам\n\n"
    "Использование: /context_mode [MODE]\n"
    "Примеры: /context_mode, /context_mode project, /context_mode acl_mentions, /context_mode global"
)

# Быстрый выбор режимов через клавиатуру
mode_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="/context_mode project"), KeyboardButton(text="/context_mode acl_mentions")],
        [KeyboardButton(text="/context_mode global")],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

@router.message(Command("context_mode"))
async def cmd_context_mode(message: Message, session: AsyncSession):
    repo = SessionRepository(session)
    parts = (message.text or "").split(maxsplit=1)
    # Если аргумента нет — показать текущий режим
    if len(parts) == 1:
        mode = await repo.get_context_mode(message.from_user.id)
        await message.answer(
            f"Текущий режим контекста: <b>{mode}</b>\n\n{HELP_TEXT}",
            reply_markup=mode_keyboard,
        )
        return

    desired = parts[1].strip().lower()
    if desired not in VALID_MODES:
        await message.answer(f"Неизвестный режим: {desired}\n\n{HELP_TEXT}")
        return

    ok = await repo.set_context_mode(message.from_user.id, desired)
    if not ok:
        await message.answer("Нет активной сессии. Запустите /start_session или /use_project.", reply_markup=ReplyKeyboardRemove())
        return

    warn = ""
    if desired == "acl_mentions":
        # Если нет активного проекта, предупредим (жёсткая изоляция в обработчике текста)
        sess = await repo.get_active_session(message.from_user.id)
        if not sess or not getattr(sess, "project_id", None):
            warn = "\n\n<i>Внимание: для acl_mentions требуется активный проект. Без него RAG не выполняется.</i>"

    await message.answer(
        f"Режим контекста обновлён: <b>{desired}</b>{warn}\n\n{HELP_TEXT}",
        reply_markup=ReplyKeyboardRemove(),
    )
