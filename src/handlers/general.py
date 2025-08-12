# Файл: C:\desk_top\src\handlers\general.py
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    await message.answer("Привет! Я DESK TOP, ваш персональный AI-агент. Готов начать новую сессию?")