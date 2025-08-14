# Файл: C:\desk_top\test_json_error.py
import asyncio
import sys
import json
from pathlib import Path

# --- Настройка путей для корректного импорта ---
root_dir = Path(__file__).parent
sys.path.append(str(root_dir))
# ---

from src.db.session import db_init, db
from src.db.repository import UserRepository, SessionRepository
from src.db.models import User, Session

# --- ТЕСТОВЫЕ ДАННЫЕ ---
TEST_USER_ID = 1122334455 # Уникальный ID для теста
TEST_USERNAME = "debug_user"
TEST_PROFILE = "test_profile"

async def run_test():
    """
    Изолированный тест для проверки корректной работы EncryptedType(JSON).
    """
    print("--- [ИНИЦИАЛИЗАЦИЯ]: Подключение к базе данных... ---")
    await db_init()
    
    async with db.AsyncSessionLocal() as session:
        print("--- [ШАГ 1]: Создание тестового пользователя и новой сессии... ---")
        user_repo = UserRepository(session)
        session_repo = SessionRepository(session)
        
        test_user = await user_repo.get_or_create_user(
            telegram_id=TEST_USER_ID, username=TEST_USERNAME
        )
        
        new_session = await session_repo.start_new_session(test_user, TEST_PROFILE)
        print(f"--- [ИНФО]: Создана сессия #{new_session.id} ---")
        
        print("\n--- [ШАГ 2]: Проверка типа данных 'message_history' после извлечения из БД... ---")
        
        retrieved_session = await session_repo.get_active_session(TEST_USER_ID)
        
        if retrieved_session:
            history = retrieved_session.message_history
            print(f"--- [ИНФО]: Значение 'message_history': {repr(history)} ---")
            print(f"--- [ИНФО]: Тип 'message_history': {type(history)} ---")

            # --- КЛЮЧЕВАЯ ПРОВЕРКА ---
            if isinstance(history, list):
                print("\n✅ [УСПЕХ]: Ошибка НЕ воспроизведена. 'message_history' является списком (list).")
            else:
                print("\n❌ [ОШИБКА ВОСПРОИЗВЕДЕНА]: 'message_history' не является списком.")
        else:
            print("\n❌ [ПРОВАЛ]: Не удалось получить активную сессию после создания.")

async def cleanup():
    """Полностью удаляет тестового пользователя и его сессии."""
    await db_init()
    async with db.AsyncSessionLocal() as session:
        # Сначала удаляем сессии, связанные с пользователем
        await session.execute(
            Session.__table__.delete().where(Session.user_id == TEST_USER_ID)
        )
        # Затем удаляем самого пользователя
        user = await session.get(User, TEST_USER_ID)
        if user:
            await session.delete(user)
        
        await session.commit()
        print("--- [ИНФО]: Старый тестовый пользователь и его сессии удалены. ---")


if __name__ == "__main__":
    # Сначала очистка, потом основной тест
    asyncio.run(cleanup())
    asyncio.run(run_test())