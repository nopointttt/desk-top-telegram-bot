# Файл: C:\desk_top\test_rag_pipeline.py
import asyncio
import logging
import sys
from pathlib import Path

# --- Настройка путей для корректного импорта ---
root_dir = Path(__file__).parent
sys.path.append(str(root_dir))
# ---

from src.services.llm_client import LLMClient
from src.services.rag_client import RAGClient

# --- Настройка логирования для максимальной детализации ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
)

# --- ТЕСТОВЫЕ ДАННЫЕ ---
TEST_USER_ID = 12345
TEST_SESSION_ID = 999
SAMPLE_SESSION_HISTORY = [
    {"role": "user", "content": "Расскажи про принципы SOLID"},
    {"role": "assistant", "content": "SOLID - это пять принципов ООП. Первый из них - Single Responsibility Principle..."},
    {"role": "user", "content": "Спасибо, этого пока достаточно"},
]
NEW_USER_QUERY = "Можешь подробнее рассказать о первом принципе, который мы обсуждали?"

async def run_test():
    """Выполняет полный цикл тестирования RAG-памяти."""
    
    print("\n--- [ШАГ 1: Инициализация клиентов] ---")
    llm_client = LLMClient()
    rag_client = RAGClient()
    await rag_client.initialize()
    print("--- [ШАГ 1: Завершен] ---\n")

    print("\n--- [ШАГ 2: Создание итогов (Summary)] ---")
    summary = await llm_client.get_summary(SAMPLE_SESSION_HISTORY)
    if not summary or "Не удалось" in summary:
        logging.error("Тест провален: не удалось создать итоги сессии.")
        return
    logging.info(f"Сгенерированные итоги:\n---\n{summary}\n---")
    print("--- [ШАГ 2: Завершен] ---\n")

    print("\n--- [ШАГ 3: Сохранение итогов в RAG-базу] ---")
    await rag_client.save_summary(TEST_SESSION_ID, TEST_USER_ID, summary)
    logging.info("Ожидайте, что в вашем дашборде Pinecone появится вектор с ID 'session-999'")
    print("--- [ШАГ 3: Завершен] ---\n")
    
    # Небольшая пауза, чтобы Pinecone успел проиндексировать вектор
    print("--- [ПАУЗА: Ожидание индексации в Pinecone (5 секунд)] ---\n")
    await asyncio.sleep(5)

    print("\n--- [ШАГ 4: Поиск релевантных итогов (симуляция нового запроса)] ---")
    logging.info(f"Новый запрос пользователя: '{NEW_USER_QUERY}'")
    relevant_summaries = await rag_client.find_relevant_summaries(TEST_USER_ID, NEW_USER_QUERY)
    if not relevant_summaries:
        logging.error("Тест провален: не найдено релевантных итогов.")
        return
    logging.info(f"Найденные итоги:\n---\n{relevant_summaries}\n---")
    print("--- [ШАГ 4: Завершен] ---\n")

    print("\n--- [ШАГ 5: Финальный ответ с использованием RAG-контекста] ---")
    final_response = await llm_client.get_response(
        system_prompt="Ты - полезный ассистент.",
        message_history=[],
        user_message=NEW_USER_QUERY,
        rag_context=relevant_summaries
    )
    if "ошибка" in final_response.lower():
         logging.error("Тест провален: не удалось сгенерировать финальный ответ.")
         return
    logging.info(f"Финальный ответ AI:\n---\n{final_response}\n---")
    print("--- [ШАГ 5: Завершен] ---\n")
    
    print("\n✅ [ТЕСТИРОВАНИЕ УСПЕШНО ЗАВЕРШЕНО] ✅\n")


if __name__ == "__main__":
    asyncio.run(run_test())