# Файл: C:\desk_top\src\personalization\keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

profile_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Кодер"), KeyboardButton(text="Продакт менеджер")],
        [KeyboardButton(text="Личный ассистент")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
    input_field_placeholder="Выберите один из профилей"
)