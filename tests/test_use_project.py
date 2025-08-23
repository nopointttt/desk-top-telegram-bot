# Файл: C:\desk_top\tests\test_use_project.py
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

# Добавляем корень проекта в sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.handlers import projects as hp


# ---- Моки сущностей ----
class FakeProject:
    def __init__(self, id: int, user_id: int, name: str, active_mode: str | None = None):
        self.id = id
        self.user_id = user_id
        self.name = name
        self.active_mode = active_mode


class FakeMessage:
    def __init__(self, user_id: int, text: str, username: str | None = None):
        self.from_user = SimpleNamespace(id=user_id, username=username)
        self.text = text
        self._answers: list[str] = []

    async def answer(self, text: str, reply_markup=None):
        self._answers.append(text)
        return SimpleNamespace(message_id=1)


# ---- Моки репозиториев ----
class FakeUserRepo:
    def __init__(self, _):
        pass

    async def get_or_create_user(self, telegram_id: int, username: str | None = None):
        return SimpleNamespace(telegram_id=telegram_id, username=username)


class FakeProjectRepo:
    def __init__(self, _):
        # наполним из тестов
        self._by_id: dict[int, FakeProject] = {}
        self._by_user: dict[int, list[FakeProject]] = {}

    def seed(self, projects: list[FakeProject]):
        self._by_id = {p.id: p for p in projects}
        self._by_user = {}
        for p in projects:
            self._by_user.setdefault(p.user_id, []).append(p)

    async def get_project_by_id(self, pid: int):
        return self._by_id.get(pid)

    async def get_project_by_name(self, user_id: int, name: str):
        for p in self._by_user.get(user_id, []):
            if p.name == name:
                return p
        return None

    async def list_projects(self, user_id: int):
        return list(self._by_user.get(user_id, []))


class FakeSessionRepo:
    def __init__(self, _):
        self.started = []  # (user.telegram_id, profile, project_id)
        self._session_id_seq = 100

    async def start_new_session(self, user, profile: str, project_id: int | None = None):
        self.started.append((user.telegram_id, profile, project_id))
        self._session_id_seq += 1
        return SimpleNamespace(id=self._session_id_seq)


# ---- Тесты ----
async def run_case_select_by_hash_id():
    # Проекты пользователя 1
    p1 = FakeProject(123, 1, "Alpha", active_mode="product_manager")
    proj_repo = FakeProjectRepo(None)
    proj_repo.seed([p1])

    hp.UserRepository = lambda db: FakeUserRepo(db)
    hp.ProjectRepository = lambda db: proj_repo
    sess_repo = FakeSessionRepo(None)
    hp.SessionRepository = lambda db: sess_repo

    msg = FakeMessage(user_id=1, text="/use_project #123")
    await hp.use_project(msg, session=None)

    # Проверяем ответ и запуск сессии
    assert msg._answers, "Ожидался ответ"
    last = msg._answers[-1]
    assert "Активирован проект 'Alpha' (id=123)" in last
    # Профиль должен совпадать с active_mode проекта
    assert sess_repo.started[-1] == (1, "product_manager", 123)


async def run_case_select_by_plain_id():
    p1 = FakeProject(42, 2, "Beta", active_mode=None)
    proj_repo = FakeProjectRepo(None)
    proj_repo.seed([p1])

    hp.UserRepository = lambda db: FakeUserRepo(db)
    hp.ProjectRepository = lambda db: proj_repo
    sess_repo = FakeSessionRepo(None)
    hp.SessionRepository = lambda db: sess_repo

    msg = FakeMessage(user_id=2, text="/use_project 42")
    await hp.use_project(msg, session=None)

    assert msg._answers, "Ожидался ответ"
    last = msg._answers[-1]
    assert "(id=42)" in last
    # Если active_mode=None, профиль по умолчанию coder
    assert sess_repo.started[-1] == (2, "coder", 42)


async def run_case_select_by_normalized_name():
    # Имя с юникод-вариантом
    p1 = FakeProject(7, 3, "Проeкт Α", active_mode="coder")  # здесь греческая А в конце
    proj_repo = FakeProjectRepo(None)
    proj_repo.seed([p1])

    hp.UserRepository = lambda db: FakeUserRepo(db)
    hp.ProjectRepository = lambda db: proj_repo
    sess_repo = FakeSessionRepo(None)
    hp.SessionRepository = lambda db: sess_repo

    # Вводим визуально схожее имя, отличающееся нормализацией
    msg = FakeMessage(user_id=3, text="/use_project Проект A")
    await hp.use_project(msg, session=None)

    # Должен найти по нормализованному равенству
    assert msg._answers, "Ожидался ответ"
    last = msg._answers[-1]
    assert "(id=7)" in last
    assert sess_repo.started[-1] == (3, "coder", 7)


async def run_case_suggestions_when_not_found():
    p1 = FakeProject(5, 4, "My Data", active_mode=None)
    p2 = FakeProject(6, 4, "Daily Notes", active_mode=None)
    proj_repo = FakeProjectRepo(None)
    proj_repo.seed([p1, p2])

    hp.UserRepository = lambda db: FakeUserRepo(db)
    hp.ProjectRepository = lambda db: proj_repo
    sess_repo = FakeSessionRepo(None)
    hp.SessionRepository = lambda db: sess_repo

    msg = FakeMessage(user_id=4, text="/use_project dataa")
    await hp.use_project(msg, session=None)

    assert msg._answers, "Ожидался ответ"
    last = msg._answers[-1]
    assert "Проект не найден" in last
    # Должны быть подсказки по подстроке после нормализации ("data" найдёт "My Data")
    assert "Возможные совпадения" in last


async def main():
    await run_case_select_by_hash_id()
    await run_case_select_by_plain_id()
    await run_case_select_by_normalized_name()
    await run_case_suggestions_when_not_found()
    print("OK: use_project tests passed")


if __name__ == "__main__":
    asyncio.run(main())


# ---- PyTest wrappers ----
def test_use_project_select_by_hash_id():
    asyncio.run(run_case_select_by_hash_id())


def test_use_project_select_by_plain_id():
    asyncio.run(run_case_select_by_plain_id())


def test_use_project_select_by_normalized_name():
    asyncio.run(run_case_select_by_normalized_name())


def test_use_project_suggestions_when_not_found():
    asyncio.run(run_case_suggestions_when_not_found())
