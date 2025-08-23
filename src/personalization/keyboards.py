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

# --- НОВЫЙ КОД ---
confirm_deletion_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Да, удалить все мои данные")],
        [KeyboardButton(text="Отмена")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)
# --- КОНЕЦ НОВОГО КОДА ---

# --- НОВЫЙ КОД: Проекты ---
project_mode_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Кодер"), KeyboardButton(text="Продакт менеджер")],
        [KeyboardButton(text="Личный ассистент")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
    input_field_placeholder="Выберите режим (роль) проекта"
)

confirm_project_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Создать проект")],
        [KeyboardButton(text="Отмена")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

skip_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Пропустить")]],
    resize_keyboard=True,
    one_time_keyboard=True
)
# --- КОНЕЦ НОВОГО КОДА ---