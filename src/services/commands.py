# Файл: C:\desk_top\src\services\commands.py
from aiogram.types import BotCommand


def get_main_menu_commands() -> list[BotCommand]:
    return [
        BotCommand(command='start', description='▶️ Запустить/перезапустить бота'),
        BotCommand(command='personalize', description='👤 Настроить профиль агента'),
        BotCommand(command='new_project', description='🧩 Создать новый проект-агент'),
        BotCommand(command='projects', description='📂 Список ваших проектов'),
        BotCommand(command='use_project', description='🔀 Переключиться на проект'),
        BotCommand(command='mode_list', description='🧪 Список модов активного проекта'),
        BotCommand(command='mode_new', description='➕ Создать мод в активном проекте'),
        BotCommand(command='mode_use', description='✅ Активировать мод для проекта/сессии'),
        BotCommand(command='mode_update', description='✏️ Обновить настройки мода'),
        BotCommand(command='mode_delete', description='🗑️ Удалить мод'),
        BotCommand(command='mode_info', description='ℹ️ Информация о текущем моде'),
        BotCommand(command='mode_unset', description='🚫 Снять мод из сессии'),
        BotCommand(command='current', description='ℹ️ Текущая сессия и проект'),
        BotCommand(command='pin_status', description='📌 Закрепить статус (проект/режим)'),
        BotCommand(command='rename_project', description='✏️ Переименовать проект'),
        BotCommand(command='delete_project', description='🗑️ Удалить проект (--force)'),
        BotCommand(command='context_mode', description='🎛️ Режим контекста: project|acl_mentions|global'),
        BotCommand(command='grant_access', description='🔐 Выдать доступ: OWNER ALLOWED [SCOPE]'),
        BotCommand(command='revoke_access', description='🔒 Отозвать доступ: OWNER ALLOWED'),
        BotCommand(command='list_access', description='📜 Список доступов: [OWNER]'),
        BotCommand(command='start_session', description='🚀 Начать новую сессию'),
        BotCommand(command='end_session', description='🛑 Завершить текущую сессию'),
        BotCommand(command='list_sessions', description='📋 Показать историю сессий'),
        BotCommand(command='export_data', description='📥 Скачать свои данные'),
        BotCommand(command='delete_my_data', description='🗑️ Удалить все свои данные'),
    ]
