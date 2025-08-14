# Файл: C:\desk_top\src\services\llm_client.py
import logging
import tiktoken
from openai import AsyncOpenAI, RateLimitError, APITimeoutError, APIConnectionError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

# Определяем, какие ошибки считать временными и требующими повторной попытки
RETRYABLE_OPENAI_ERRORS = (RateLimitError, APITimeoutError, APIConnectionError)

class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        try:
            self.encoding = tiktoken.encoding_for_model("gpt-4o")
        except Exception as e:
            logger.warning(f"Could not get encoding for gpt-4o, falling back to cl100k_base. Error: {e}")
            self.encoding = tiktoken.get_encoding("cl100k_base")
        logger.info("LLMClient initialized.")

    def count_tokens(self, text: str) -> int:
        """Подсчитывает количество токенов в строке."""
        if not text:
            return 0
        return len(self.encoding.encode(text))

    @retry(
        stop=stop_after_attempt(3), # Максимум 3 попытки
        wait=wait_exponential(multiplier=1, min=2, max=10), # Ожидание: 2с, 4с, 8с...
        retry=retry_if_exception_type(RETRYABLE_OPENAI_ERRORS) # Повторять только при определенных ошибках
    )
    async def get_response(
        self, system_prompt: str, message_history: list, user_message: str, rag_context: list[str] = None
    ) -> str:
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
            
            usage = response.usage
            if usage:
                logger.info(
                    f"OpenAI API Call (get_response): "
                    f"Prompt Tokens={usage.prompt_tokens}, "
                    f"Completion Tokens={usage.completion_tokens}, "
                    f"Total Tokens={usage.total_tokens}"
                )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error communicating with OpenAI: {e}")
            raise # Перевыбрасываем ошибку, чтобы tenacity мог ее поймать

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(RETRYABLE_OPENAI_ERRORS)
    )
    async def get_summary(self, message_history: list) -> str:
        summary_prompt = (
            "Подведи краткие, но емкие итоги этого диалога для "
            "сохранения в базу знаний. Сконцентрируйся на ключевых фактах, "
            "решениях и выводах. Текст должен быть в формате markdown."
        )
        messages = message_history + [{"role": "user", "content": summary_prompt}]

        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo", messages=messages
            )
            
            usage = response.usage
            if usage:
                logger.info(
                    f"OpenAI API Call (get_summary): "
                    f"Prompt Tokens={usage.prompt_tokens}, "
                    f"Completion Tokens={usage.completion_tokens}, "
                    f"Total Tokens={usage.total_tokens}"
                )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error creating summary: {e}")
            raise # Перевыбрасываем ошибку, чтобы tenacity мог ее поймать