# Файл: C:\desk_top\src\services\llm_client.py
import logging
from openai import AsyncOpenAI
from src.config import OPENAI_API_KEY

class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        logging.info("LLMClient initialized.")

    async def get_response(self, system_prompt: str, message_history: list, user_message: str) -> str:
        """
        Отправляет запрос к LLM и возвращает текстовый ответ.
        """
        # TODO: Добавить логику RAG для обогащения контекста
        
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        # TODO: Добавить историю сообщений `message_history`
        messages.append({"role": "user", "content": user_message})

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"Error communicating with OpenAI: {e}")
            return "Произошла ошибка при обращении к AI. Пожалуйста, попробуйте позже."