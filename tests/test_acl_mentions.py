# Файл: C:\desk_top\tests\test_acl_mentions.py
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

# Добавляем корень проекта в sys.path, чтобы работал импорт src.* при прямом запуске файла
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Импортируем модуль обработчика, затем будем монкипатчить его зависимости
from src.handlers import session as session_handler
from src.services import prompt_builder as prompt_builder_module


# ---- Моки окружения ----
class FakeMessage:
    def __init__(self, user_id: int, text: str, username: str | None = None):
        self.from_user = SimpleNamespace(id=user_id, username=username)
        self.text = text
        self.chat = SimpleNamespace(id=777)
        self._answers = []

    async def answer(self, text: str, reply_markup=None):
        sm = FakeStatusMessage(self.chat.id, text)
        self._answers.append(text)
        return sm


class FakeStatusMessage:
    def __init__(self, chat_id: int, text: str):
        self.chat = SimpleNamespace(id=chat_id)
        self.message_id = 1
        self._text = text

    async def edit_text(self, text: str):
        self._text = text


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id: int, text: str):
        self.sent.append((chat_id, text))

    async def pin_chat_message(self, chat_id: int, message_id: int, disable_notification=True):
        # не используется в тестах
        pass


class FakeLLMClient:
    def count_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    async def get_response(self, system_prompt, history, user_message, rag_context=None, temperature=None):
        return f"RESP::{len(rag_context or [])}::TEMP={temperature}"


class FakeRAGClient:
    def __init__(self):
        self.calls = []

    async def find_relevant_summaries(self, user_id: int, query: str, project_id=None, project_ids=None):
        self.calls.append({
            'user_id': user_id,
            'project_id': project_id,
            'project_ids': list(project_ids) if project_ids else None,
        })
        # Возвращаем N фиктивных итогов (зависит от project_ids для наглядности)
        n = 0
        if project_ids:
            n = len(project_ids)
        elif project_id is not None:
            n = 1
        else:
            n = 2
        return [f"summary_{i}" for i in range(n)]


# ---- Фейковые репозитории ----
class _FakeSessionObj:
    def __init__(self, project_id: int | None, context_mode: str, message_history=None, mode_id=None):
        self.id = 42
        self.user_id = 123
        self.project_id = project_id
        self.context_mode = context_mode
        self.message_history = message_history or []
        self.mode_id = mode_id
        self.active_profile = 'coder'
        self.created_at = SimpleNamespace(strftime=lambda fmt: '2025-01-01 10:00')


class FakeSessionRepository:
    def __init__(self, _):
        self._active = None

    async def get_active_session(self, user_id: int):
        return self._active

    async def set_active(self, s: _FakeSessionObj):
        self._active = s

    async def get_context_mode(self, user_id: int) -> str:
        return self._active.context_mode if self._active else 'project'

    async def update_message_history(self, session_id: int, new_message: dict):
        # для теста не требуется сохранять
        pass


class FakeProject:
    def __init__(self, pid: int, name: str):
        self.id = pid
        self.name = name


class FakeProjectRepository:
    def __init__(self, _):
        # карта name -> project
        self._by_name = {}
        self._by_id = {}

    def seed(self, projects):
        for p in projects:
            self._by_name[p.name] = p
            self._by_id[p.id] = p

    async def get_project_by_id(self, project_id: int):
        return self._by_id.get(project_id)

    async def get_project_by_name(self, user_id: int, name: str):
        return self._by_name.get(name)


class FakeProjectAccessRepository:
    def __init__(self, _):
        self._allowed = set()  # парой (owner_id, allowed_id)

    def seed(self, pairs):
        self._allowed |= set(pairs)

    async def is_allowed(self, owner_project_id: int, target_project_id: int, required_scope: str = 'read') -> bool:
        return (owner_project_id, target_project_id) in self._allowed


class FakeUserRepository:
    def __init__(self, _):
        pass

    async def get_or_create_user(self, telegram_id: int, username: str | None = None):
        return SimpleNamespace(telegram_id=telegram_id, username=username)

    async def check_and_update_limits(self, user, tokens_to_add: int) -> bool:
        return True


class FakePromptRepo:
    def __init__(self, _):
        pass

    async def get_prompt(self, user_id: int, profile: str) -> str | None:
        return "SYSTEM"


async def run_case_no_active_project():
    # Монкипатчим зависимости модуля
    session_handler.UserRepository = FakeUserRepository
    session_handler.SessionRepository = FakeSessionRepository
    session_handler.ProjectRepository = FakeProjectRepository
    session_handler.ProjectAccessRepository = FakeProjectAccessRepository
    session_handler.PersonalizedPromptRepository = FakePromptRepo
    prompt_builder_module.PersonalizedPromptRepository = FakePromptRepo

    # Контекст: acl_mentions, НЕТ активного проекта
    sess_repo = FakeSessionRepository(None)
    await sess_repo.set_active(_FakeSessionObj(project_id=None, context_mode='acl_mentions', message_history=[]))

    # Вкалываем наш репозиторий в модульный namespace, чтобы handler создал именно его и увидел активную сессию
    def _factory_session_repo(db):
        return sess_repo
    session_handler.SessionRepository = lambda db: _factory_session_repo(db)

    rag = FakeRAGClient()
    llm = FakeLLMClient()
    bot = FakeBot()
    msg = FakeMessage(user_id=123, text="Привет @[Other]")

    await session_handler.handle_text_message(msg, session=None, bot=bot, llm_client=llm, rag_client=rag)

    # Проверка: RAG не вызывался
    assert len(rag.calls) == 0, f"RAG must not be called, got {rag.calls}"


async def run_case_mentions_without_acl():
    # Монкипатчим
    session_handler.UserRepository = FakeUserRepository
    session_handler.SessionRepository = FakeSessionRepository
    session_handler.ProjectRepository = FakeProjectRepository
    session_handler.ProjectAccessRepository = FakeProjectAccessRepository
    session_handler.PersonalizedPromptRepository = FakePromptRepo
    prompt_builder_module.PersonalizedPromptRepository = FakePromptRepo

    # Активный проект P1, контекст acl_mentions. В базе есть проект Other, но ACL нет.
    sess_repo = FakeSessionRepository(None)
    await sess_repo.set_active(_FakeSessionObj(project_id=1, context_mode='acl_mentions', message_history=[{"role":"user","content":"hi"}]))
    proj_repo = FakeProjectRepository(None)
    proj_repo.seed([FakeProject(1, 'P1'), FakeProject(2, 'Other')])

    acl_repo = FakeProjectAccessRepository(None)  # без seed, значит ACL нет

    session_handler.SessionRepository = lambda db: sess_repo
    session_handler.ProjectRepository = lambda db: proj_repo
    session_handler.ProjectAccessRepository = lambda db: acl_repo

    rag = FakeRAGClient()
    llm = FakeLLMClient()
    bot = FakeBot()
    msg = FakeMessage(user_id=123, text="Дай контекст @[Other]")

    await session_handler.handle_text_message(msg, session=None, bot=bot, llm_client=llm, rag_client=rag)

    # Проверка: RAG вызван 1 раз с project_ids=[1] (только активный проект)
    assert len(rag.calls) == 1, f"RAG must be called once, got {len(rag.calls)}"
    call = rag.calls[0]
    assert call['project_ids'] == [1], f"Expected only active project [1], got {call['project_ids']}"


async def run_case_mentions_with_acl():
    # Монкипатчим
    session_handler.UserRepository = FakeUserRepository
    session_handler.SessionRepository = FakeSessionRepository
    session_handler.ProjectRepository = FakeProjectRepository
    session_handler.ProjectAccessRepository = FakeProjectAccessRepository
    session_handler.PersonalizedPromptRepository = FakePromptRepo
    prompt_builder_module.PersonalizedPromptRepository = FakePromptRepo

    # Активный проект P1, есть Other и Third. ACL выдан к Other, к Third — нет.
    sess_repo = FakeSessionRepository(None)
    await sess_repo.set_active(_FakeSessionObj(project_id=1, context_mode='acl_mentions', message_history=[{"role":"user","content":"hi"}]))
    proj_repo = FakeProjectRepository(None)
    proj_repo.seed([FakeProject(1, 'P1'), FakeProject(2, 'Other'), FakeProject(3, 'Third')])
    acl_repo = FakeProjectAccessRepository(None)
    acl_repo.seed({(1, 2)})  # P1 -> Other разрешен

    session_handler.SessionRepository = lambda db: sess_repo
    session_handler.ProjectRepository = lambda db: proj_repo
    session_handler.ProjectAccessRepository = lambda db: acl_repo

    rag = FakeRAGClient()
    llm = FakeLLMClient()
    bot = FakeBot()
    msg = FakeMessage(user_id=123, text="Дай контекст @[Other] и @[Third]")

    await session_handler.handle_text_message(msg, session=None, bot=bot, llm_client=llm, rag_client=rag)

    # Проверка: RAG вызван 1 раз с project_ids=[1,2] (активный + с ACL), Third проигнорирован
    assert len(rag.calls) == 1, f"RAG must be called once, got {len(rag.calls)}"
    call = rag.calls[0]
    assert call['project_ids'] == [1, 2], f"Expected [1,2], got {call['project_ids']}"


async def main():
    await run_case_no_active_project()
    await run_case_mentions_without_acl()
    await run_case_mentions_with_acl()
    print("OK: acl_mentions tests passed")


if __name__ == "__main__":
    asyncio.run(main())
