# Файл: C:\desk_top\src\services\llm_client.py
import logging
import tiktoken
from openai import AsyncOpenAI, RateLimitError, APITimeoutError, APIConnectionError, APIStatusError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception, retry_if_exception_type
from src.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

# Определяем, какие ошибки считать временными и требующими повторной попытки
RETRYABLE_OPENAI_ERRORS = (RateLimitError, APITimeoutError, APIConnectionError, APIStatusError)

class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        try:
            self.encoding = tiktoken.encoding_for_model("gpt-4o")
        except Exception as e:
            logger.warning(f"Could not get encoding for gpt-4o, falling back to cl100k_base. Error: {e}")
            self.encoding = tiktoken.get_encoding("cl100k_base")
        logger.info("LLMClient initialized.")

        # Мягкие лимиты под 128k контекст моделей семейства gpt-4o
        self.MODEL_NAME = "gpt-4o"
        # Окно контекста модели (приблизительно). Держим запас под completion
        self.MODEL_CONTEXT_WINDOW = 128_000
        # Максимум токенов на completion
        self.MAX_COMPLETION_TOKENS = 2_048
        # Бюджет на prompt (system+history+user+RAG), оставляем запас под completion
        self.MAX_PROMPT_TOKENS = max(self.MODEL_CONTEXT_WINDOW - self.MAX_COMPLETION_TOKENS, 80_000)
        # Доли распределения бюджета между RAG и историей
        self.RAG_BUDGET_RATIO = 0.6  # 60% RAG, 40% история
        # Таймаут запроса к OpenAI, сек
        self.REQUEST_TIMEOUT = 30

    def _clamp_temperature(self, temperature: float | None) -> float | None:
        if temperature is None:
            return None
        try:
            t = float(temperature)
        except Exception:
            return None
        # Ограничиваем диапазон совместимый с OpenAI
        if t < 0.0:
            t = 0.0
        if t > 2.0:
            t = 2.0
        return t

    def count_tokens(self, text: str) -> int:
        """Подсчитывает количество токенов в строке."""
        if not text:
            return 0
        return len(self.encoding.encode(text))

    def _fit_rag_context(self, items: list[str], token_budget: int) -> list[str]:
        """Возвращает подмножество items, укладывающееся в token_budget (с начала списка)."""
        if not items or token_budget <= 0:
            return []
        selected = []
        used = 0
        sep_tokens = self.count_tokens("\n\n")
        for i, s in enumerate(items):
            t = self.count_tokens(s)
            add = t if i == 0 else t + sep_tokens
            if used + add > token_budget:
                break
            selected.append(s)
            used += add
        return selected

    def _fit_history_tail(self, history: list[dict], token_budget: int) -> list[dict]:
        """Берем последние сообщения истории (с конца), пока укладываемся в token_budget."""
        if not history or token_budget <= 0:
            return []
        acc: list[dict] = []
        used = 0
        # идем с конца — недавние сообщения важнее
        for msg in reversed(history):
            content = msg.get("content", "")
            t = self.count_tokens(content)
            if used + t > token_budget:
                break
            acc.append(msg)
            used += t
        acc.reverse()
        return acc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(lambda e: isinstance(e, RETRYABLE_OPENAI_ERRORS) and getattr(getattr(e, 'status', None), '__int__', lambda: None)() in (None, 429, 500, 502, 503, 504))
    )
    async def get_response(
        self, system_prompt: str, message_history: list, user_message: str, rag_context: list[str] = None, temperature: float | None = None
    ) -> str:
        # Подсчет базовых токенов без истории и RAG
        user_tokens = self.count_tokens(user_message)
        system_base_tokens = self.count_tokens(system_prompt)

        # Бюджет под RAG и историю
        remain = max(self.MAX_PROMPT_TOKENS - (system_base_tokens + user_tokens), 0)
        rag_selected: list[str] = []
        history_selected: list[dict] = []

        # Сначала RAG (важнее для фактов), затем история
        if rag_context:
            rag_budget = int(remain * self.RAG_BUDGET_RATIO)
            rag_selected = self._fit_rag_context(rag_context, rag_budget)
            rag_tokens = self.count_tokens("\n\n".join(rag_selected))
        else:
            rag_tokens = 0

        remain_after_rag = max(remain - rag_tokens, 0)
        history_selected = self._fit_history_tail(message_history or [], remain_after_rag)

        # Собираем финальный system с включенным RAG
        if rag_selected:
            rag_info = "\n\n".join(rag_selected)
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
        messages.extend(history_selected)
        messages.append({"role": "user", "content": user_message})

        try:
            kwargs = {
                "model": self.MODEL_NAME,
                "messages": messages,
                "max_tokens": self.MAX_COMPLETION_TOKENS,
                "timeout": self.REQUEST_TIMEOUT,
            }
            t = self._clamp_temperature(temperature)
            if t is not None:
                kwargs["temperature"] = t
            # В некоторых версиях SDK timeout задается через with_options
            client = self.client.with_options(timeout=self.REQUEST_TIMEOUT)
            response = await client.chat.completions.create(**kwargs)
            
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