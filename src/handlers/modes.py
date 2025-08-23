# Файл: C:\desk_top\src\handlers\modes.py
import json
import logging
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repository import UserRepository, ProjectRepository, SessionRepository, ModeRepository

router = Router()
logger = logging.getLogger(__name__)

# FSM для интерактивного создания мода в рамках активного проекта
class NewMode(StatesGroup):
    entering_name = State()
    entering_system_prompt = State()
    entering_tools_config = State()
    entering_temperature = State()


async def _require_active_project(message: Message, session: AsyncSession):
    """Возвращает (user, project) текущей активной сессии. Отвечает ошибкой, если не найдено."""
    user_repo = UserRepository(session)
    proj_repo = ProjectRepository(session)
    sess_repo = SessionRepository(session)

    user = await user_repo.get_or_create_user(message.from_user.id, message.from_user.username)
    active = await sess_repo.get_active_session(user.telegram_id)
    if not active or not active.project_id:
        await message.answer("Нет активного проекта. Используйте /use_project или /new_project.")
        return None, None, None, None
    project = await proj_repo.get_project_by_id(active.project_id)
    return user, project, active, (user_repo, proj_repo, sess_repo)


@router.message(Command("mode_list"))
async def mode_list(message: Message, session: AsyncSession):
    user, project, _, _repos = await _require_active_project(message, session)
    if not project:
        return
    mode_repo = ModeRepository(session)
    modes = await mode_repo.list_modes(project.id)
    if not modes:
        await message.answer(f"В проекте '{project.name}' нет модов. Создайте: /mode_new")
        return
    lines = [f"Моды проекта '{project.name}':"]
    for m in modes:
        mark = "⭐ " if project.active_mode and project.active_mode == m.name else "  "
        lines.append(f"{mark}{m.name} (id={m.id})")
    await message.answer("\n".join(lines))


@router.message(Command("mode_new"))
async def mode_new_start(message: Message, state: FSMContext, session: AsyncSession):
    _, project, _, _ = await _require_active_project(message, session)
    if not project:
        return
    await state.clear()
    await state.set_state(NewMode.entering_name)
    await message.answer("Имя мода (уникально в проекте):", reply_markup=ReplyKeyboardRemove())


@router.message(NewMode.entering_name, F.text.len() > 0)
async def mode_new_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Имя не может быть пустым. Введите имя мода:")
        return
    await state.update_data(name=name)
    await state.set_state(NewMode.entering_system_prompt)
    await message.answer("Системный промпт мода (или напишите 'Пропустить'):")


@router.message(NewMode.entering_system_prompt)
async def mode_new_system_prompt(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    system_prompt = None if txt.lower() == "пропустить" else txt
    await state.update_data(system_prompt=system_prompt)
    await state.set_state(NewMode.entering_tools_config)
    await message.answer("JSON настроек инструментов (или 'Пропустить'):")


@router.message(NewMode.entering_tools_config)
async def mode_new_tools(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    tools_config = None
    if txt and txt.lower() != "пропустить":
        # не валидируем схему, только проверим JSON
        try:
            json.loads(txt)
            tools_config = txt
        except json.JSONDecodeError:
            await message.answer("Невалидный JSON. Введите корректный JSON или 'Пропустить':")
            return
    await state.update_data(tools_config=tools_config)
    await state.set_state(NewMode.entering_temperature)
    await message.answer("Температура (например, 0.2) или 'Пропустить':")


@router.message(NewMode.entering_temperature)
async def mode_new_temperature(message: Message, state: FSMContext, session: AsyncSession):
    txt = (message.text or "").strip()
    temperature = None
    if txt.lower() != "пропустить":
        try:
            val = float(txt.replace(',', '.'))
            if val < 0.0 or val > 2.0:
                await message.answer("Температура должна быть числом от 0.0 до 2.0. Введите снова или 'Пропустить':")
                return
            # Клампинг и нормализация формата
            val = max(0.0, min(2.0, val))
            temperature = f"{val:.3f}".rstrip('0').rstrip('.')
        except ValueError:
            await message.answer("Температура должна быть числом (напр., 0.2). Введите снова или 'Пропустить':")
            return
    data = await state.get_data()

    user, project, _, _ = await _require_active_project(message, session)
    if not project:
        return
    mode_repo = ModeRepository(session)
    try:
        md = await mode_repo.create_mode(
            project_id=project.id,
            name=data["name"],
            system_prompt=data.get("system_prompt"),
            tools_config=data.get("tools_config"),
            temperature=temperature,
        )
    except ValueError as e:
        await message.answer(str(e))
        return

    await state.clear()
    await message.answer(f"Мод '{md.name}' создан (id={md.id}) для проекта '{project.name}'.")


@router.message(Command("mode_use"))
async def mode_use(message: Message, session: AsyncSession):
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Использование: /mode_use ИМЯ_МОДА (в рамках активного проекта)")
        return
    target_name = parts[1].strip()

    user, project, active_session, repos = await _require_active_project(message, session)
    if not project:
        return
    user_repo, proj_repo, sess_repo = repos
    mode_repo = ModeRepository(session)

    md = await mode_repo.get_mode_by_name(project.id, target_name)
    if not md:
        await message.answer("Мод не найден в активном проекте. Посмотрите /mode_list.")
        return

    # 1) Установить активный мод на проекте
    try:
        await proj_repo.set_active_mode(project.id, md.name)
    except ValueError as e:
        await message.answer(str(e))
        return

    # 2) Обновить текущую активную сессию: привязать mode_id
    if active_session:
        active_session.mode_id = md.id
        await session.commit()

    await message.answer(f"Активирован мод '{md.name}' для проекта '{project.name}'.")


@router.message(Command("mode_update"))
async def mode_update(message: Message, session: AsyncSession):
    """/mode_update <name> key=value ...  (keys: system_prompt, temperature[0..2], tools_config(JSON))"""
    text = (message.text or "").strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Использование: /mode_update <имя> key=value ...")
        return
    name = parts[1].strip()
    kv = parts[2].strip()

    _, project, _, _ = await _require_active_project(message, session)
    if not project:
        return
    mode_repo = ModeRepository(session)
    md = await mode_repo.get_mode_by_name(project.id, name)
    if not md:
        await message.answer("Мод не найден.")
        return

    updates = {}
    # простой разбор a=b c=d (без кавычек)
    for token in kv.split():
        if "=" not in token:
            continue
        k, v = token.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k == "system_prompt":
            updates["system_prompt"] = v
        elif k == "temperature":
            try:
                val = float(v.replace(',', '.'))
                if val < 0.0 or val > 2.0:
                    await message.answer("temperature должна быть в диапазоне [0.0 .. 2.0]")
                    return
                val = max(0.0, min(2.0, val))
                updates["temperature"] = f"{val:.3f}".rstrip('0').rstrip('.')
            except ValueError:
                await message.answer("temperature должна быть числом (например, 0.2)")
                return
        elif k == "tools_config":
            # проверим JSON
            try:
                json.loads(v)
                updates["tools_config"] = v
            except json.JSONDecodeError:
                await message.answer("tools_config должен быть валидным JSON")
                return
    if not updates:
        await message.answer("Не распознаны ключи. Разрешены: system_prompt, temperature, tools_config")
        return

    md2 = await mode_repo.update_mode(md.id, **updates)
    await message.answer(f"Мод '{md2.name}' обновлён.")


@router.message(Command("mode_delete"))
async def mode_delete(message: Message, session: AsyncSession):
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Использование: /mode_delete ИМЯ_МОДА")
        return
    target_name = parts[1].strip()

    user, project, _, repos = await _require_active_project(message, session)
    if not project:
        return
    _, proj_repo, _ = repos
    mode_repo = ModeRepository(session)

    md = await mode_repo.get_mode_by_name(project.id, target_name)
    if not md:
        await message.answer("Мод не найден.")
        return

    # Если удаляем активный мод, снимем активный на проекте
    if project.active_mode == md.name:
        await proj_repo.set_active_mode(project.id, None)
    ok = await mode_repo.delete_mode(md.id)
    if not ok:
        await message.answer("Мод не удалён (не найден).")
        return
    await message.answer(f"Мод '{target_name}' удалён из проекта '{project.name}'.")


# --- New: /mode_info ---
@router.message(Command("mode_info"))
async def mode_info(message: Message, session: AsyncSession):
    """Показывает активный мод текущей сессии (Session.mode_id) и активный мод проекта."""
    user_repo = UserRepository(session)
    proj_repo = ProjectRepository(session)
    sess_repo = SessionRepository(session)
    mode_repo = ModeRepository(session)

    user = await user_repo.get_or_create_user(message.from_user.id, message.from_user.username)
    active = await sess_repo.get_active_session(user.telegram_id)
    if not active:
        await message.answer("Нет активной сессии. Используйте /start_session.")
        return

    project_line = "проект: —"
    proj_mode_line = "проект-мод: —"
    if active.project_id:
        project = await proj_repo.get_project_by_id(active.project_id)
        if project:
            project_line = f"проект: {project.name} (id={project.id})"
            proj_mode_line = f"проект-мод: {project.active_mode or 'n/a'}"

    sess_mode_line = "сессия-мод: n/a"
    if getattr(active, 'mode_id', None):
        md = await mode_repo.get_mode_by_id(active.mode_id)
        if md:
            t = f", t={md.temperature}" if md.temperature not in (None, "") else ""
            sess_mode_line = f"сессия-мод: {md.name}{t} (id={md.id})"
            # покажем tools_config коротко
            if md.tools_config:
                try:
                    parsed = json.loads(md.tools_config)
                    preview = json.dumps(parsed, ensure_ascii=False)[:400]
                except Exception:
                    preview = (md.tools_config or "")[:400]
                sess_mode_line += f"\ntools: {preview}..."

    await message.answer("\n".join([
        "Информация о режиме:",
        project_line,
        proj_mode_line,
        sess_mode_line,
    ]))


# --- New: /mode_unset ---
@router.message(Command("mode_unset"))
async def mode_unset(message: Message, session: AsyncSession):
    """Снимает активный мод у текущей сессии (Session.mode_id = NULL). Проект не изменяется."""
    user_repo = UserRepository(session)
    sess_repo = SessionRepository(session)

    user = await user_repo.get_or_create_user(message.from_user.id, message.from_user.username)
    active = await sess_repo.get_active_session(user.telegram_id)
    if not active:
        await message.answer("Нет активной сессии. Используйте /start_session.")
        return

    if getattr(active, 'mode_id', None) is None:
        await message.answer("В сессии не установлен мод.")
        return

    active.mode_id = None
    await session.commit()
    await message.answer("Сессионный мод снят (Session.mode_id = NULL). Проект-мод не изменён.")
