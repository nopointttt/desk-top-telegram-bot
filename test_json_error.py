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
from src.db.models import User

# --- ТЕСТОВЫЕ ДАННЫЕ ---
TEST_USER_ID = 1122334455 # Уникальный ID для теста
TEST_USERNAME = "debug_user"
TEST_PROFILE = "test_profile"

async def run_test():
    """
    Изолированный тест для воспроизведения ошибки JSONDecodeError.
    """
    print("--- [ИНИЦИАЛИЗАЦИЯ]: Подключение к базе данных... ---")
    await db_init()
    
    # Получаем сессию БД напрямую для теста
    async with db.AsyncSessionLocal() as session:
        print("--- [ШАГ 1]: Создание тестового пользователя и новой сессии... ---")
        user_repo = UserRepository(session)
        session_repo = SessionRepository(session)
        
        test_user = await user_repo.get_or_create_user(
            telegram_id=TEST_USER_ID, username=TEST_USERNAME
        )
        
        # Вызываем тот самый метод, который используется в боте
        new_session = await session_repo.start_new_session(test_user, TEST_PROFILE)
        
        print(f"--- [ИНФО]: Создана сессия #{new_session.id} ---")
        
        print("\n--- [ШАГ 2]: Попытка прочитать 'message_history' из созданной сессии... ---")
        
        retrieved_session = await session_repo.get_active_session(TEST_USER_ID)
        
        if retrieved_session:
            print(f"--- [ИНФО]: Значение 'message_history' в базе данных: {repr(retrieved_session.message_history)} ---")
            try:
                # Пытаемся выполнить операцию, которая вызывает сбой в боте
                json.loads(retrieved_session.message_history)
                print("\n✅ [УСПЕХ]: Ошибка НЕ воспроизведена. 'message_history' содержит корректный JSON.")
            except json.JSONDecodeError as e:
                print("\n❌ [ОШИБКА ВОСПРОИЗВЕДЕНА]: Попытка обработать пустое (NULL) значение 'message_history' провалилась.")
                print(f"   Тип ошибки: {type(e)}")
                print(f"   Сообщение: {e}")
        else:
            print("\n❌ [ПРОВАЛ]: Не удалось получить активную сессию после создания.")

if __name__ == "__main__":
    # Удаляем старого тестового пользователя, если он есть, для чистоты эксперимента
    async def cleanup():
        await db_init()
        async with db.AsyncSessionLocal() as session:
            user_repo = UserRepository(session)
            user = await session.get(User, TEST_USER_ID)
            if user:
                await session.delete(user)
                await session.commit()
                print("--- [ИНФО]: Старый тестовый пользователь удален. ---")

    # Сначала очистка, потом основной тест
    asyncio.run(cleanup())
    asyncio.run(run_test())