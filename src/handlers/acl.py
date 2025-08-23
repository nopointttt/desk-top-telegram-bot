# Файл: C:\desk_top\src\handlers\acl.py
import logging
import re
import unicodedata
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repository import (
    UserRepository,
    ProjectRepository,
    SessionRepository,
    ProjectAccessRepository,
)

router = Router()
logger = logging.getLogger(__name__)


def _norm(s: str) -> str:
    """Unicode-нормализация + casefold + trim для сравнения имён.
    Не меняет исходные имена, только для поиска/сравнения.
    """
    return unicodedata.normalize("NFKC", (s or "").strip()).casefold()


async def resolve_project(
    proj_repo: ProjectRepository,
    user_id: int,
    ident: str,
):
    """Резолвит проект пользователя по идентификатору:
    - "#123" или "123" -> по id
    - точное имя
    - case-insensitive/Unicode-normalized совпадение среди проектов пользователя
    Возвращает кортеж (project_or_none, suggestions_list).
    """
    ident = (ident or "").strip()
    if not ident:
        return None, []

    # 1) По ID
    if re.fullmatch(r"#?\d+", ident):
        pid = int(ident.lstrip('#'))
        p = await proj_repo.get_project_by_id(pid)
        return (p, []) if (p and p.user_id == user_id) else (None, [])

    # 2) Точное имя
    p = await proj_repo.get_project_by_name(user_id, ident)
    if p:
        return p, []

    # 3) Нормализованный поиск среди всех проектов пользователя
    projects = await proj_repo.list_projects(user_id)
    ident_n = _norm(ident)
    for pr in projects:
        if _norm(pr.name) == ident_n:
            return pr, []

    # 4) Предложить похожие (подстрока после нормализации)
    sugg = [pr.name for pr in projects if ident_n and ident_n in _norm(pr.name)]
    return None, sugg[:5]


@router.message(Command("grant_access"))
async def cmd_grant_access(message: Message, session: AsyncSession):
    """Выдать межпроектный доступ: /grant_access OWNER_NAME ALLOWED_NAME [SCOPE]
    Пример: /grant_access ПроектА ПроектБ read
    По умолчанию scope=read.
    """
    text = (message.text or "").strip()
    parts = text.split(maxsplit=3)
    if len(parts) < 3:
        await message.answer("Использование: /grant_access OWNER_NAME ALLOWED_NAME [SCOPE]")
        return

    owner_name = parts[1].strip()
    allowed_name = parts[2].strip()
    scope = parts[3].strip() if len(parts) >= 4 else "read"

    user_repo = UserRepository(session)
    proj_repo = ProjectRepository(session)
    acl_repo = ProjectAccessRepository(session)

    user = await user_repo.get_or_create_user(message.from_user.id, message.from_user.username)

    if owner_name == allowed_name:
        await message.answer("Нельзя выдавать доступ проекту к самому себе")
        return

    owner, owner_sugg = await resolve_project(proj_repo, user.telegram_id, owner_name)
    allowed, allowed_sugg = await resolve_project(proj_repo, user.telegram_id, allowed_name)
    if not owner:
        hint = ("\nВозможные совпадения: " + ", ".join(owner_sugg)) if owner_sugg else ""
        await message.answer(f"Проект '{owner_name}' не найден у вас.{hint}")
        return
    if not allowed:
        hint = ("\nВозможные совпадения: " + ", ".join(allowed_sugg)) if allowed_sugg else ""
        await message.answer(f"Проект '{allowed_name}' не найден у вас.{hint}")
        return

    try:
        pa = await acl_repo.grant_access(owner.id, allowed.id, scope=scope)
        await message.answer(
            f"Разрешён доступ: '{owner.name}' -> '{allowed.name}' (scope={pa.scope})."
        )
    except Exception as e:
        logger.error(f"grant_access error: {e}")
        await message.answer("Не удалось выдать доступ. Проверьте параметры и повторите.")


@router.message(Command("revoke_access"))
async def cmd_revoke_access(message: Message, session: AsyncSession):
    """Отозвать доступ: /revoke_access OWNER_NAME ALLOWED_NAME"""
    text = (message.text or "").strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Использование: /revoke_access OWNER_NAME ALLOWED_NAME")
        return

    owner_name = parts[1].strip()
    allowed_name = parts[2].strip()

    user_repo = UserRepository(session)
    proj_repo = ProjectRepository(session)
    acl_repo = ProjectAccessRepository(session)

    user = await user_repo.get_or_create_user(message.from_user.id, message.from_user.username)

    owner, owner_sugg = await resolve_project(proj_repo, user.telegram_id, owner_name)
    allowed, allowed_sugg = await resolve_project(proj_repo, user.telegram_id, allowed_name)
    if not owner:
        hint = ("\nВозможные совпадения: " + ", ".join(owner_sugg)) if owner_sugg else ""
        await message.answer(f"Проект '{owner_name}' не найден у вас.{hint}")
        return
    if not allowed:
        hint = ("\nВозможные совпадения: " + ", ".join(allowed_sugg)) if allowed_sugg else ""
        await message.answer(f"Проект '{allowed_name}' не найден у вас.{hint}")
        return

    ok = await acl_repo.revoke_access(owner.id, allowed.id)
    if ok:
        await message.answer(f"Доступ отозван: '{owner.name}' -X-> '{allowed.name}'.")
    else:
        await message.answer("Такого доступа не было.")


@router.message(Command("list_access"))
async def cmd_list_access(message: Message, session: AsyncSession):
    """Показать выданные доступы: /list_access OWNER_NAME
    Если имя не указано — берётся активный проект текущей сессии.
    """
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)

    user_repo = UserRepository(session)
    proj_repo = ProjectRepository(session)
    sess_repo = SessionRepository(session)
    acl_repo = ProjectAccessRepository(session)

    user = await user_repo.get_or_create_user(message.from_user.id, message.from_user.username)

    owner = None
    if len(parts) >= 2 and parts[1].strip():
        owner_name = parts[1].strip()
        owner, owner_sugg = await resolve_project(proj_repo, user.telegram_id, owner_name)
        if not owner:
            hint = ("\nВозможные совпадения: " + ", ".join(owner_sugg)) if owner_sugg else ""
            await message.answer(f"Проект '{owner_name}' не найден у вас.{hint}")
            return
    else:
        active = await sess_repo.get_active_session(user.telegram_id)
        if not active or not active.project_id:
            await message.answer("Укажите OWNER_NAME: /list_access OWNER_NAME (нет активного проекта)")
            return
        owner = await proj_repo.get_project_by_id(active.project_id)
        if not owner:
            await message.answer("Активный проект не найден.")
            return

    access_rows = await acl_repo.list_access(owner.id)
    if not access_rows:
        await message.answer(f"У проекта '{owner.name}' нет выданных доступов.")
        return

    lines = [f"Доступы, выданные проектом '{owner.name}':"]
    # Для удобства — показать имена проектов назначения
    for pa in access_rows:
        target = await proj_repo.get_project_by_id(pa.allowed_project_id)
        target_name = target.name if target else f"id={pa.allowed_project_id}"
        lines.append(f"- {target_name} (scope={pa.scope})")

    await message.answer("\n".join(lines))


@router.message(Command("door_check"))
async def cmd_door_check(message: Message, session: AsyncSession):
    """Проверка двери ACL: /door_check [OWNER_NAME] ALLOWED_NAME
    Если OWNER_NAME не указан — используется активный проект текущей сессии.
    Возвращает 'allowed' или 'denied'.
    """
    text = (message.text or "").strip()
    parts = text.split(maxsplit=2)

    user_repo = UserRepository(session)
    proj_repo = ProjectRepository(session)
    sess_repo = SessionRepository(session)
    acl_repo = ProjectAccessRepository(session)

    user = await user_repo.get_or_create_user(message.from_user.id, message.from_user.username)

    owner = None
    allowed_name = None
    if len(parts) == 2:
        # без OWNER_NAME: только ALLOWED_NAME
        allowed_name = parts[1].strip()
        active = await sess_repo.get_active_session(user.telegram_id)
        if not active or not active.project_id:
            await message.answer("Укажите OWNER_NAME: /door_check OWNER_NAME ALLOWED_NAME (нет активного проекта)")
            return
        owner = await proj_repo.get_project_by_id(active.project_id)
        if not owner:
            await message.answer("Активный проект не найден.")
            return
    elif len(parts) >= 3:
        owner_name = parts[1].strip()
        allowed_name = parts[2].strip()
        owner, owner_sugg = await resolve_project(proj_repo, user.telegram_id, owner_name)
        if not owner:
            hint = ("\nВозможные совпадения: " + ", ".join(owner_sugg)) if owner_sugg else ""
            await message.answer(f"Проект '{owner_name}' не найден у вас.{hint}")
            return
    else:
        await message.answer("Использование: /door_check [OWNER_NAME] ALLOWED_NAME")
        return

    allowed, allowed_sugg = await resolve_project(proj_repo, user.telegram_id, allowed_name)
    if not allowed:
        hint = ("\nВозможные совпадения: " + ", ".join(allowed_sugg)) if allowed_sugg else ""
        await message.answer(f"Проект '{allowed_name}' не найден у вас.{hint}")
        return

    is_ok = await acl_repo.is_allowed(owner.id, allowed.id)
    status = "allowed" if is_ok else "denied"
    await message.answer(f"ACL door: '{owner.name}' -> '{allowed.name}' = {status}")
