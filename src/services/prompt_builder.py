# Файл: C:\desk_top\src\services\prompt_builder.py
import json
from typing import Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.models import Mode, Project, Session as DbSession
from src.db.repository import PersonalizedPromptRepository


async def _format_tools_block(tools_config: Optional[str]) -> str:
    if not tools_config:
        return ""
    block = tools_config
    try:
        block = json.dumps(json.loads(tools_config), ensure_ascii=False, indent=2)
    except Exception:
        pass
    return f"\n\n[Tools Configuration]\n{block}"


async def build_prompt(
    db: AsyncSession,
    user_id: int,
    active_session: DbSession,
    active_project: Optional[Project],
) -> Tuple[str, Optional[float]]:
    """
    Строит system_prompt и возвращает (prompt, temperature).
    Приоритет источников:
      1) Mode (из Session.mode_id): переопределяет system_prompt, добавляет tools_config, задаёт temperature
      2) Project.system_prompt
      3) PersonalizedPrompt по active_profile
    Все операции асинхронные, без блокировок.
    """
    # 1) Базовый system_prompt: Project.system_prompt или PersonalizedPrompt
    if active_project and getattr(active_project, 'system_prompt', None):
        system_prompt: str = active_project.system_prompt
    else:
        prompt_repo = PersonalizedPromptRepository(db)
        system_prompt = await prompt_repo.get_prompt(user_id, active_session.active_profile)
        if not system_prompt:
            raise ValueError("Профиль не настроен. Начните с /personalize")

    temperature: Optional[float] = None

    # 2) Если выбран Mode на сессии — применяем
    try:
        m_id = getattr(active_session, 'mode_id', None)
        if m_id:
            res = await db.execute(select(Mode).where(Mode.id == m_id))
            mode = res.scalar_one_or_none()
            if mode:
                if getattr(mode, 'system_prompt', None):
                    system_prompt = mode.system_prompt
                tools_block = await _format_tools_block(getattr(mode, 'tools_config', None))
                if tools_block:
                    system_prompt = f"{system_prompt}{tools_block}"
                temp_val = getattr(mode, 'temperature', None)
                if temp_val is not None:
                    try:
                        temperature = float(temp_val)
                    except Exception:
                        temperature = None
    except Exception:
        # Не блокируем диалог при проблемах с Mode
        pass

    return system_prompt, temperature
