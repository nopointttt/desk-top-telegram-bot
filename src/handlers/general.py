# Файл: C:\desk_top\src\handlers\general.py
from aiogram import Router
from aiogram.types import Message, BotCommand
from aiogram.filters import CommandStart, Command
from aiogram import Bot
from src.services.commands import get_main_menu_commands

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    await message.answer("Привет! Я DESK TOP, ваш персональный AI-агент. Готов начать новую сессию?")

@router.message(Command("refresh_commands"))
async def refresh_commands(message: Message, bot: Bot):
    """Принудительно обновляет список команд бота без перезапуска."""
    await bot.set_my_commands(get_main_menu_commands())
    await message.answer("Список команд обновлен. Откройте меню команд или введите / чтобы увидеть актуальные команды.")