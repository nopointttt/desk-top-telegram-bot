# Файл: C:\desk_top\src\handlers\projects.py
import json
import logging
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.personalization.states import NewProject
from src.personalization.keyboards import (
    project_mode_keyboard,
    confirm_project_keyboard,
    skip_keyboard,
)
from src.db.repository import UserRepository, ProjectRepository, SessionRepository
from src.services.llm_client import LLMClient

router = Router()
logger = logging.getLogger(__name__)

PROFILE_MAP_RU_TO_KEY = {
    "Кодер": "coder",
    "Продакт менеджер": "product_manager",
    "Личный ассистент": "personal_assistant",
}

# --- Helpers ---

import re
import unicodedata

def _norm(s: str) -> str:
    """Unicode NFKC + casefold + trim + упрощённая латинизация конфузаблов.
    Важно: делаем только безопасные подстановки визуально-сходных символов
    в ASCII, чтобы улучшить поиск по имени между кириллицей/греческими буквами.
    Не влияет на исходные данные в БД, используется только для сравнения/поиска.
    """
    base = unicodedata.normalize("NFKC", (s or "").strip()).casefold()
    # Частые конфузаблы: кириллические и греческие буквы, похожие на латиницу
    confusables = {
        # Cyrillic -> Latin
        "а": "a",  # U+0430
        "е": "e",  # U+0435
        "о": "o",  # U+043E
        "р": "r",  # U+0440
        "с": "c",  # U+0441
        "у": "y",  # U+0443
        "х": "x",  # U+0445
        "к": "k",  # U+043A
        "т": "t",  # U+0442
        "в": "v",  # U+0432
        "м": "m",  # U+043C
        "н": "n",  # U+043D
        # Greek -> Latin (минимально необходимое)
        "α": "a",  # alpha
        "β": "b",
        "γ": "g",
        "δ": "d",
        "ε": "e",
        "η": "h",
        "ι": "i",
        "κ": "k",
        "λ": "l",
        "μ": "m",
        "ν": "n",
        "ο": "o",
        "π": "p",
        "ρ": "r",
        "τ": "t",
        "υ": "y",
        "χ": "x",
        "ο": "o",
    }
    # Применяем замену посимвольно
    return "".join(confusables.get(ch, ch) for ch in base)

def _build_system_prompt(name: str, goal: str | None, context: str | None, mode_key: str) -> str:
    role_map = {
        "coder": "Software Engineer",
        "product_manager": "Product Manager",
        "personal_assistant": "Personal Assistant",
    }
    role = role_map.get(mode_key, "Generalist")
    parts = [
        f"You are an autonomous project agent for project '{name}'.",
        f"Primary role: {role}.",
        "Operate with strict context isolation. Never leak data between projects unless explicitly instructed with a cross-project door.",
    ]
    if goal:
        parts.append(f"Project goal: {goal}")
    if context:
        parts.append(f"Context: {context}")
    parts.extend([
        "Behaviors:",
        "- Plan, reason step-by-step with compact internal notes.",
        "- Retrieve short-term context from recent session messages.",
        "- Retrieve long-term knowledge via RAG (Pinecone) filtered by this project.",
        "- Ask clarifying questions if information is missing.",
        "- Always provide actionable, concise outputs.",
    ])
    return "\n".join(parts)


def _initial_backlog(goal: str | None) -> str:
    items = []
    if goal:
        items = [
            {"title": "Clarify acceptance criteria", "status": "todo"},
            {"title": "Identify key knowledge sources", "status": "todo"},
            {"title": "Draft first milestone plan", "status": "todo"},
        ]
    return json.dumps(items, ensure_ascii=False)


# --- FSM: /new_project ---
@router.message(Command("new_project"))
async def new_project_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(NewProject.entering_name)
    await message.answer(
        "Название проекта? (уникально в рамках вашего аккаунта)",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(NewProject.entering_name, F.text.len() > 0)
async def new_project_name(message: Message, state: FSMContext, session: AsyncSession):
    name = message.text.strip()
    if name.lower() in {"отмена", "cancel"}:
        await state.clear()
        await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())
        return
    user_repo = UserRepository(session)
    proj_repo = ProjectRepository(session)
    user = await user_repo.get_or_create_user(message.from_user.id, message.from_user.username)
    existing = await proj_repo.get_project_by_name(user.telegram_id, name)
    if existing:
        await message.answer("Проект с таким именем уже есть. Введите другое имя:")
        return
    await state.update_data(name=name)
    await state.set_state(NewProject.entering_goal)
    await message.answer("Кратко опишите цель проекта (или нажмите 'Пропустить'):", reply_markup=skip_keyboard)


@router.message(NewProject.entering_goal)
async def new_project_goal(message: Message, state: FSMContext):
    txt = message.text or ""
    if txt.lower() in {"отмена", "cancel"}:
        await state.clear()
        await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())
        return
    goal = None if txt.strip().lower() == "пропустить" else txt.strip()
    await state.update_data(goal=goal)
    await state.set_state(NewProject.entering_context)
    await message.answer("Добавьте контекст/ограничения (или 'Пропустить'):", reply_markup=skip_keyboard)


@router.message(NewProject.entering_context)
async def new_project_context(message: Message, state: FSMContext):
    txt = message.text or ""
    if txt.lower() in {"отмена", "cancel"}:
        await state.clear()
        await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())
        return
    context = None if txt.strip().lower() == "пропустить" else txt.strip()
    await state.update_data(context=context)
    await state.set_state(NewProject.choosing_mode)
    await message.answer("Выберите режим проекта:", reply_markup=project_mode_keyboard)


@router.message(NewProject.choosing_mode, F.text.in_({"Кодер", "Продакт менеджер", "Личный ассистент"}))
async def new_project_mode(message: Message, state: FSMContext):
    mode_key = PROFILE_MAP_RU_TO_KEY[message.text]
    await state.update_data(mode=mode_key)
    data = await state.get_data()
    summary = [
        f"Имя: {data.get('name')}",
        f"Цель: {data.get('goal') or '—'}",
        f"Контекст: {data.get('context') or '—'}",
        f"Режим: {message.text}",
    ]
    await state.set_state(NewProject.confirming)
    await message.answer("\n".join(["Проверьте детали проекта:"] + summary), reply_markup=confirm_project_keyboard)


@router.message(NewProject.confirming, F.text == "Создать проект")
async def new_project_confirm(message: Message, state: FSMContext, session: AsyncSession, llm_client: LLMClient):
    data = await state.get_data()
    name = data.get("name")
    goal = data.get("goal")
    context = data.get("context")
    mode_key = data.get("mode")

    user_repo = UserRepository(session)
    proj_repo = ProjectRepository(session)
    sess_repo = SessionRepository(session)

    user = await user_repo.get_or_create_user(message.from_user.id, message.from_user.username)

    # Генерация system_prompt/backlog (без блокирующих вызовов; LLM по желанию)
    system_prompt = _build_system_prompt(name, goal, context, mode_key)
    backlog = _initial_backlog(goal)

    try:
        project = await proj_repo.create_project(
            user_id=user.telegram_id,
            name=name,
            goal=goal,
            context=context,
            active_mode=mode_key,
            system_prompt=system_prompt,
            backlog=backlog,
        )
    except ValueError as e:
        await message.answer(str(e))
        return

    new_db_session = await sess_repo.start_new_session(user, profile=mode_key, project_id=project.id)

    await state.clear()
    await message.answer(
        (
            f"Проект '{project.name}' создан (id={project.id}).\n"
            f"Открыта сессия #{new_db_session.id}. Можете отправить первый запрос."
        ),
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(NewProject.confirming, F.text == "Отмена")
async def new_project_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())

# --- Commands: /projects and /use_project ---

@router.message(Command("projects"))
async def list_projects(message: Message, session: AsyncSession):
    """Список проектов пользователя с пометкой активного по текущей сессии."""
    user_repo = UserRepository(session)
    proj_repo = ProjectRepository(session)
    sess_repo = SessionRepository(session)

    user = await user_repo.get_or_create_user(message.from_user.id, message.from_user.username)
    projects = await proj_repo.list_projects(user.telegram_id)
    active = await sess_repo.get_active_session(user.telegram_id)
    active_project_id = active.project_id if active else None

    if not projects:
        await message.answer("У вас ещё нет проектов. Используйте /new_project для создания.")
        return

    lines = ["Ваши проекты:"]
    kb_rows = []
    for p in projects:
        mark = "⭐ " if p.id == active_project_id else "  "
        lines.append(f"{mark}{p.name} (id={p.id}, mode={p.active_mode or 'n/a'})")
        kb_rows.append([InlineKeyboardButton(text=f"Перейти: {p.name}", callback_data=f"use_project:{p.id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer("\n".join(lines), reply_markup=kb)


@router.message(Command("use_project"))
async def use_project(message: Message, session: AsyncSession):
    """Переключает активный проект: закрывает активную сессию и открывает новую под выбранным проектом."""
    # Извлекаем имя проекта из команды: "/use_project <name>"
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Использование: /use_project ИМЯ_ПРОЕКТА")
        return
    target_name = parts[1].strip()

    user_repo = UserRepository(session)
    proj_repo = ProjectRepository(session)
    sess_repo = SessionRepository(session)

    user = await user_repo.get_or_create_user(message.from_user.id, message.from_user.username)
    project = None
    # 1) По ID вида #123 или 123
    if re.fullmatch(r"#?\d+", target_name):
        try:
            pid = int(target_name.lstrip('#'))
            p = await proj_repo.get_project_by_id(pid)
            if p and p.user_id == user.telegram_id:
                project = p
        except Exception:
            project = None
    # 2) Точное имя
    if not project:
        project = await proj_repo.get_project_by_name(user.telegram_id, target_name)
    # 3) Нормализованное равенство среди проектов пользователя
    if not project:
        all_projects = await proj_repo.list_projects(user.telegram_id)
        tgt_n = _norm(target_name)
        for p in all_projects:
            if _norm(p.name) == tgt_n:
                project = p
                break
    if not project:
        # 4) Предложить похожие по подстроке после нормализации
        all_projects = all_projects if 'all_projects' in locals() else await proj_repo.list_projects(user.telegram_id)
        tgt_n = _norm(target_name)
        suggestions = [p.name for p in all_projects if tgt_n and tgt_n in _norm(p.name)]
        hint = ("\nВозможные совпадения: " + ", ".join(suggestions[:5])) if suggestions else ""
        await message.answer("Проект не найден. Проверьте имя или вызовите /projects для списка." + hint)
        return

    profile = project.active_mode or "coder"
    new_db_session = await sess_repo.start_new_session(user, profile=profile, project_id=project.id)
    await message.answer(
        (
            f"Активирован проект '{project.name}' (id={project.id}).\n"
            f"Открыта новая сессия #{new_db_session.id} (mode={profile}). Можете продолжать диалог."
        )
    )


@router.callback_query(F.data.startswith("use_project:"))
async def cb_use_project(call: CallbackQuery, session: AsyncSession):
    """Переключение проекта по кнопке из /projects."""
    try:
        project_id = int(call.data.split(":", 1)[1])
    except Exception:
        await call.answer("Некорректный идентификатор проекта", show_alert=True)
        return

    user_repo = UserRepository(session)
    proj_repo = ProjectRepository(session)
    sess_repo = SessionRepository(session)

    user = await user_repo.get_or_create_user(call.from_user.id, call.from_user.username)
    project = await proj_repo.get_project_by_id(project_id)
    if not project or project.user_id != user.telegram_id:
        await call.answer("Проект не найден", show_alert=True)
        return
    profile = project.active_mode or "coder"
    new_db_session = await sess_repo.start_new_session(user, profile=profile, project_id=project.id)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(
        (
            f"Активирован проект '{project.name}' (id={project.id}).\n"
            f"Открыта новая сессия #{new_db_session.id} (mode={profile})."
        )
    )
    await call.answer("Проект активирован")


@router.message(Command("rename_project"))
async def rename_project(message: Message, session: AsyncSession):
    """Переименовать проект пользователя: /rename_project <old_name> <new_name>"""
    text = (message.text or "").strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].strip() or not parts[2].strip():
        await message.answer("Использование: /rename_project <старое_имя> <новое_имя>")
        return
    old_name, new_name = parts[1].strip(), parts[2].strip()

    user_repo = UserRepository(session)
    proj_repo = ProjectRepository(session)
    user = await user_repo.get_or_create_user(message.from_user.id, message.from_user.username)

    try:
        proj = await proj_repo.rename_project(user.telegram_id, old_name, new_name)
    except ValueError as e:
        await message.answer(str(e))
        return

    await message.answer(f"Проект переименован: '{old_name}' → '{proj.name}' (id={proj.id}).")


@router.message(Command("delete_project"))
async def delete_project(message: Message, session: AsyncSession):
    """Удалить проект пользователя: /delete_project <name> --force
    Требуется явный флаг --force для предотвращения случайного удаления.
    """
    text = (message.text or "").strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Использование: /delete_project ИМЯ_ПРОЕКТА --force")
        return
    name = parts[1].strip()
    force = "--force" in text
    if not force:
        await message.answer(
            "Удаление проекта приведёт к удалению связанных сессий.\n"
            "Это действие необратимо. Чтобы подтвердить, выполните: /delete_project <имя> --force"
        )
        return

    user_repo = UserRepository(session)
    proj_repo = ProjectRepository(session)
    sess_repo = SessionRepository(session)
    user = await user_repo.get_or_create_user(message.from_user.id, message.from_user.username)

    # Если удаляется активный проект — закрываем активную сессию (она удалится каскадом, но статус завершим явно)
    active = await sess_repo.get_active_session(user.telegram_id)
    if active and active.project_id:
        proj = await proj_repo.get_project_by_id(active.project_id)
        if proj and proj.name == name:
            await sess_repo.close_all_active_sessions(user.telegram_id)

    ok = await proj_repo.delete_project(user.telegram_id, name)
    if not ok:
        await message.answer("Проект не найден.")
        return
    await message.answer(f"Проект '{name}' удалён.")
