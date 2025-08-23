# Файл: C:\desk_top\tests\test_context_mode.py
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

# Добавляем корень проекта в sys.path для импорта src.*
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Импортируем модуль обработчика
from src.handlers import context_mode as cm


# ---- Моки окружения ----
class FakeMessage:
    def __init__(self, user_id: int, text: str, username: str | None = None):
        self.from_user = SimpleNamespace(id=user_id, username=username)
        self.text = text
        self.chat = SimpleNamespace(id=777)
        self._answers: list[str] = []

    async def answer(self, text: str, reply_markup=None):
        # Сохраняем только текст для простоты проверок
        self._answers.append(text)
        return SimpleNamespace(chat=SimpleNamespace(id=self.chat.id), message_id=1)


class FakeSessionObj:
    def __init__(self, project_id: int | None):
        self.project_id = project_id


class FakeSessionRepository:
    def __init__(self, _):
        # Значения по умолчанию, можно перенастраивать из тестов
        self._mode = "project"
        self._active_session = FakeSessionObj(project_id=None)
        self._settable = True

    async def get_context_mode(self, user_id: int) -> str:
        return self._mode

    async def set_context_mode(self, user_id: int, mode: str) -> bool:
        if not self._settable:
            return False
        self._mode = mode
        return True

    async def get_active_session(self, user_id: int):
        return self._active_session


# ---- Тест-кейсы ----
async def run_case_show_current_mode():
    repo = FakeSessionRepository(None)
    repo._mode = "acl_mentions"
    cm.SessionRepository = lambda db: repo

    msg = FakeMessage(user_id=123, text="/context_mode")
    await cm.cmd_context_mode(msg, session=None)

    assert msg._answers, "Ожидали ответ от /context_mode"
    assert "acl_mentions" in msg._answers[-1], f"Должны показать текущий режим, получили: {msg._answers[-1]}"


async def run_case_invalid_mode():
    repo = FakeSessionRepository(None)
    cm.SessionRepository = lambda db: repo

    msg = FakeMessage(user_id=123, text="/context_mode unknown_mode")
    await cm.cmd_context_mode(msg, session=None)

    assert msg._answers, "Ожидали ответ для неверного режима"
    assert "Неизвестный режим" in msg._answers[-1]


async def run_case_no_active_session_on_set():
    repo = FakeSessionRepository(None)
    repo._settable = False  # имитируем отсутствие активной сессии
    cm.SessionRepository = lambda db: repo

    msg = FakeMessage(user_id=123, text="/context_mode project")
    await cm.cmd_context_mode(msg, session=None)

    assert msg._answers, "Ожидали ответ при отсутствии активной сессии"
    assert "Нет активной сессии" in msg._answers[-1]


async def run_case_acl_mentions_warn_without_project():
    repo = FakeSessionRepository(None)
    repo._active_session = FakeSessionObj(project_id=None)  # нет активного проекта
    cm.SessionRepository = lambda db: repo

    msg = FakeMessage(user_id=123, text="/context_mode acl_mentions")
    await cm.cmd_context_mode(msg, session=None)

    assert msg._answers, "Ожидали ответ об обновлении режима"
    last = msg._answers[-1]
    assert "Режим контекста обновлён" in last
    assert "acl_mentions" in last
    assert "требуется активный проект" in last, f"Ожидали предупреждение, получили: {last}"


async def main():
    await run_case_show_current_mode()
    await run_case_invalid_mode()
    await run_case_no_active_session_on_set()
    await run_case_acl_mentions_warn_without_project()
    print("OK: context_mode tests passed")


if __name__ == "__main__":
    asyncio.run(main())


# ---- PyTest wrappers ----
def test_context_mode_show_current_mode():
    asyncio.run(run_case_show_current_mode())


def test_context_mode_invalid_mode():
    asyncio.run(run_case_invalid_mode())


def test_context_mode_no_active_session_on_set():
    asyncio.run(run_case_no_active_session_on_set())


def test_context_mode_acl_mentions_warn_without_project():
    asyncio.run(run_case_acl_mentions_warn_without_project())
