# Файл: C:\desk_top\src\services\llm_client.py
import logging
import tiktoken
from openai import AsyncOpenAI
from src.config import OPENAI_API_KEY

class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        # --- НОВЫЙ КОД ---
        try:
            self.encoding = tiktoken.encoding_for_model("gpt-4o")
        except Exception as e:
            logging.warning(f"Could not get encoding for gpt-4o, falling back to cl100k_base. Error: {e}")
            self.encoding = tiktoken.get_encoding("cl100k_base")
        # --- КОНЕЦ НОВОГО КОДА ---
        logging.info("LLMClient initialized.")

    def count_tokens(self, text: str) -> int:
        """Подсчитывает количество токенов в строке."""
        return len(self.encoding.encode(text))

    async def get_response(
        self, system_prompt: str, message_history: list, user_message: str, rag_context: list[str] = None
    ) -> str:
        # ... (этот метод без изменений)
        if rag_context:
            rag_info = "\n\n".join(rag_context)
            system_prompt_with_rag = (
                f"{system_prompt}\n\n"
                f"Для ответа на текущий вопрос пользователя ты ДОЛЖЕН использовать следующий контекст из вашей с ним прошлой беседы. "
                f"Это твоя долгосрочная память. Ссылайся на нее, как будто вы только что это обсуждали.\n"
                f"--- КОНТЕКСТ ИЗ ПАМЯТИ ---\n"
                f"{rag_info}\n"
                f"--- КОНЕЦ КОНТЕКСТА ---\n"
            )
        else:
            system_prompt_with_rag = system_prompt
        messages = [{"role": "system", "content": system_prompt_with_rag}]
        messages.extend(message_history)
        messages.append({"role": "user", "content": user_message})
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o", messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"Error communicating with OpenAI: {e}")
            return "Произошла ошибка при обращении к AI."

    async def get_summary(self, message_history: list) -> str:
        # ... (этот метод без изменений)
        summary_prompt = (
            "Подведи краткие, но емкие итоги этого диалога для "
            "сохранения в базу знаний. Сконцентрируйся на ключевых фактах, "
            "решениях и выводах. Текст должен быть в формате markdown."
        )
        messages = message_history
        messages.append({"role": "user", "content": summary_prompt})
        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo", messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"Error creating summary: {e}")
            return "Не удалось создать итоги сессии."