# Файл: C:/desk_top/src/db/repository.py
import datetime
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from src.db.models import User, Session, PersonalizedPrompt, Project, ProjectAccess, Mode
from src.config import DAILY_TOKEN_LIMIT

class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_user(self, telegram_id: int, username: str = None) -> User:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            new_user = User(telegram_id=telegram_id, username=username)
            self.session.add(new_user)
            await self.session.commit()
            await self.session.refresh(new_user)
            return new_user
        return user

    async def delete_all_user_data(self, telegram_id: int):
        await self.session.execute(
            delete(PersonalizedPrompt).where(PersonalizedPrompt.user_id == telegram_id)
        )
        await self.session.execute(
            delete(Session).where(Session.user_id == telegram_id)
        )
        # Удаляем проекты явно, т.к. ORM-каскад не сработает при bulk DELETE
        await self.session.execute(
            delete(Project).where(Project.user_id == telegram_id)
        )
        await self.session.execute(
            delete(User).where(User.telegram_id == telegram_id)
        )
        await self.session.commit()
        logging.info(f"All data for user {telegram_id} has been deleted.")

    async def check_and_update_limits(self, user: User, tokens_to_add: int) -> bool:
        today = datetime.date.today()
        if user.last_request_date != today:
            user.tokens_used_today = 0
            user.last_request_date = today
        if user.tokens_used_today + tokens_to_add > DAILY_TOKEN_LIMIT:
            logging.warning(f"User {user.telegram_id} has exceeded the daily token limit.")
            return False
        user.tokens_used_today += tokens_to_add
        await self.session.commit()
        return True

class ProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_project_by_name(self, user_id: int, name: str) -> Project | None:
        stmt = select(Project).where(Project.user_id == user_id, Project.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_project_by_id(self, project_id: int) -> Project | None:
        stmt = select(Project).where(Project.id == project_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_projects(self, user_id: int) -> list[Project]:
        stmt = select(Project).where(Project.user_id == user_id).order_by(Project.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_project(
        self,
        user_id: int,
        name: str,
        goal: str | None = None,
        context: str | None = None,
        active_mode: str | None = None,
        system_prompt: str | None = None,
        backlog: str | None = None,
    ) -> Project:
        # Enforce unique name per user
        existing = await self.get_project_by_name(user_id, name)
        if existing:
            raise ValueError(f"Project with name '{name}' already exists for this user")
        project = Project(
            user_id=user_id,
            name=name,
            goal=goal,
            context=context,
            active_mode=active_mode,
            system_prompt=system_prompt,
            backlog=backlog,
        )
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def update_project(self, project_id: int, **fields) -> Project | None:
        proj = await self.get_project_by_id(project_id)
        if not proj:
            return None
        for k, v in fields.items():
            if hasattr(proj, k) and v is not None:
                setattr(proj, k, v)
        await self.session.commit()
        await self.session.refresh(proj)
        return proj

    async def rename_project(self, user_id: int, old_name: str, new_name: str) -> Project:
        """Переименовать проект пользователя с проверкой уникальности имени."""
        proj = await self.get_project_by_name(user_id, old_name)
        if not proj:
            raise ValueError("Проект не найден")
        existing = await self.get_project_by_name(user_id, new_name)
        if existing:
            raise ValueError("Проект с таким именем уже существует")
        proj.name = new_name
        await self.session.commit()
        await self.session.refresh(proj)
        return proj

    async def delete_project(self, user_id: int, name: str) -> bool:
        """Удаляет проект пользователя по имени. Возвращает True, если удалён.
        Удаление выполняется через ORM, каскад удалит связанные сессии (см. модели).
        """
        proj = await self.get_project_by_name(user_id, name)
        if not proj:
            return False
        await self.session.delete(proj)
        await self.session.commit()
        return True

    async def set_active_mode(self, project_id: int, mode_name: str | None) -> Project | None:
        """Устанавливает активный мод проекта (по имени мода в рамках проекта).
        Если mode_name=None — снимает активный мод.
        """
        proj = await self.get_project_by_id(project_id)
        if not proj:
            return None
        if mode_name is None:
            proj.active_mode = None
        else:
            # Проверим, что такой мод существует в проекте
            stmt = select(Mode).where(Mode.project_id == project_id, Mode.name == mode_name)
            res = await self.session.execute(stmt)
            md = res.scalar_one_or_none()
            if not md:
                raise ValueError("Mode with this name not found in the project")
            proj.active_mode = mode_name
        await self.session.commit()
        await self.session.refresh(proj)
        return proj

class PersonalizedPromptRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_or_update_prompt(self, user_id: int, profile: str, prompt_text: str):
        stmt = select(PersonalizedPrompt).where(
            PersonalizedPrompt.user_id == user_id,
            PersonalizedPrompt.profile == profile
        )
        result = await self.session.execute(stmt)
        existing_prompt = result.scalar_one_or_none()
        if existing_prompt:
            existing_prompt.prompt_text = prompt_text
        else:
            existing_prompt = PersonalizedPrompt(
                user_id=user_id, profile=profile, prompt_text=prompt_text
            )
            self.session.add(existing_prompt)
        await self.session.commit()

    async def get_prompt(self, user_id: int, profile: str) -> str | None:
        stmt = select(PersonalizedPrompt.prompt_text).where(
            PersonalizedPrompt.user_id == user_id,
            PersonalizedPrompt.profile == profile
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

class SessionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _deserialize_history(self, session_obj: Session) -> Session:
        """
        Приватный метод для десериализации истории из строки в список.
        Теперь устойчив к некорректным JSON-данным.
        """
        if session_obj and session_obj.message_history:
            history_val = session_obj.message_history
            try:
                if isinstance(history_val, str):
                    session_obj.message_history = json.loads(history_val)
                elif isinstance(history_val, bytes):
                    session_obj.message_history = json.loads(history_val.decode('utf-8'))
            except json.JSONDecodeError:
                logging.error(f"Failed to decode message_history for session_id={session_obj.id}. Treating as empty.")
                session_obj.message_history = []
        elif session_obj:
            session_obj.message_history = []
        return session_obj

    async def close_all_active_sessions(self, user_id: int):
        stmt = select(Session).where(Session.user_id == user_id, Session.status == 'active')
        result = await self.session.execute(stmt)
        active_sessions = result.scalars().all()
        for s in active_sessions:
            s.status = 'closed'
            s.ended_at = datetime.datetime.utcnow()
        if active_sessions:
            await self.session.commit()

    async def start_new_session(self, user: User, profile: str, project_id: int | None = None) -> Session:
        await self.close_all_active_sessions(user.telegram_id)
        mode_id: int | None = None
        if project_id is not None:
            # Попытаемся подтянуть mode_id из Project.active_mode
            proj_stmt = select(Project).where(Project.id == project_id)
            proj_res = await self.session.execute(proj_stmt)
            proj = proj_res.scalar_one_or_none()
            if proj and proj.active_mode:
                md_stmt = select(Mode).where(Mode.project_id == project_id, Mode.name == proj.active_mode)
                md_res = await self.session.execute(md_stmt)
                md = md_res.scalar_one_or_none()
                if md:
                    mode_id = md.id

        new_session = Session(
            user_id=user.telegram_id,
            status='active',
            active_profile=profile,
            project_id=project_id,
            mode_id=mode_id,
            message_history=json.dumps([])
        )
        self.session.add(new_session)
        await self.session.commit()
        await self.session.refresh(new_session)
        return self._deserialize_history(new_session)
        
    async def get_active_session(self, user_id: int) -> Session | None:
        stmt = select(Session).where(Session.user_id == user_id, Session.status == 'active')
        result = await self.session.execute(stmt)
        session = result.scalar_one_or_none()
        return self._deserialize_history(session)

    async def get_context_mode(self, user_id: int) -> str:
        """Возвращает режим контекста активной сессии пользователя или 'project' по умолчанию."""
        s = await self.get_active_session(user_id)
        if s and getattr(s, 'context_mode', None):
            return s.context_mode
        return 'project'

    async def set_context_mode(self, user_id: int, mode: str) -> bool:
        """Устанавливает режим контекста для активной сессии. Возвращает True при успехе."""
        s = await self.get_active_session(user_id)
        if not s:
            return False
        s.context_mode = mode
        await self.session.commit()
        return True

    async def list_sessions(self, user_id: int) -> list[Session]:
        stmt = select(Session).where(Session.user_id == user_id).order_by(Session.created_at.desc())
        result = await self.session.execute(stmt)
        sessions = result.scalars().all()
        return [self._deserialize_history(s) for s in sessions]

    async def update_message_history(self, session_id: int, new_message: dict):
        active_session = await self.session.get(Session, session_id)
        if active_session:
            history_val = active_session.message_history
            if isinstance(history_val, list):
                history_list = history_val
            elif isinstance(history_val, str):
                history_list = json.loads(history_val or '[]')
            elif isinstance(history_val, bytes):
                 history_list = json.loads(history_val.decode('utf-8') or '[]')
            else:
                history_list = []
            history_list.append(new_message)
            active_session.message_history = json.dumps(history_list, ensure_ascii=False)
            await self.session.commit()

    async def delete_old_sessions(self, days: int = 30):
        logging.info(f"Running scheduled job: Deleting sessions older than {days} days.")
        cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        stmt = delete(Session).where(
            Session.status == 'closed',
            Session.ended_at < cutoff_date
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        if result.rowcount > 0:
            logging.info(f"Deleted {result.rowcount} old sessions.")


class ProjectAccessRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def grant_access(self, owner_project_id: int, allowed_project_id: int, scope: str = 'read') -> ProjectAccess:
        """Выдаёт доступ owner_project -> allowed_project. Идемпотентно по паре id."""
        if owner_project_id == allowed_project_id:
            raise ValueError("Нельзя выдавать доступ проекту к самому себе")
        # Проверим существование (уникальный индекс на паре полей)
        stmt = select(ProjectAccess).where(
            ProjectAccess.owner_project_id == owner_project_id,
            ProjectAccess.allowed_project_id == allowed_project_id,
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            # Обновим scope при необходимости
            if existing.scope != scope:
                existing.scope = scope
                await self.session.commit()
                await self.session.refresh(existing)
            return existing
        pa = ProjectAccess(owner_project_id=owner_project_id, allowed_project_id=allowed_project_id, scope=scope)
        self.session.add(pa)
        await self.session.commit()
        await self.session.refresh(pa)
        return pa

    async def revoke_access(self, owner_project_id: int, allowed_project_id: int) -> bool:
        """Отзывает доступ. Возвращает True, если запись была удалена."""
        stmt = select(ProjectAccess).where(
            ProjectAccess.owner_project_id == owner_project_id,
            ProjectAccess.allowed_project_id == allowed_project_id,
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        if not existing:
            return False
        await self.session.delete(existing)
        await self.session.commit()
        return True

    async def list_access(self, owner_project_id: int) -> list[ProjectAccess]:
        """Список доступов, выданных данным owner-проектом."""
        stmt = select(ProjectAccess).where(ProjectAccess.owner_project_id == owner_project_id).order_by(ProjectAccess.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_allowed_projects_for(self, owner_project_id: int) -> list[int]:
        """Список project_id, к которым owner-проект имеет доступ."""
        stmt = select(ProjectAccess.allowed_project_id).where(ProjectAccess.owner_project_id == owner_project_id)
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def is_allowed(self, owner_project_id: int, target_project_id: int, required_scope: str = 'read') -> bool:
        """Проверяет наличие доступа. Пока scope — плоский, без иерархии."""
        stmt = select(ProjectAccess).where(
            ProjectAccess.owner_project_id == owner_project_id,
            ProjectAccess.allowed_project_id == target_project_id,
        )
        res = await self.session.execute(stmt)
        pa = res.scalar_one_or_none()
        return pa is not None


def _normalize_temperature(value) -> str | None:
    """
    Нормализует температуру к строке в диапазоне [0.0..2.0] с 3 знаками после запятой
    (обрезание завершающих нулей и точки). Возвращает None, если значение пустое.
    Бросает ValueError при нечисловом вводе.
    """
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        if v == "":
            return None
        v = v.replace(",", ".")
        try:
            f = float(v)
        except ValueError:
            raise ValueError("temperature must be a number in [0.0..2.0]")
    elif isinstance(value, (int, float)):
        f = float(value)
    else:
        raise ValueError("temperature has unsupported type")
    if f < 0.0 or f > 2.0:
        raise ValueError("temperature out of range [0.0..2.0]")
    f = max(0.0, min(2.0, f))
    s = f"{f:.3f}".rstrip('0').rstrip('.')
    return s

class ModeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_modes(self, project_id: int) -> list[Mode]:
        stmt = select(Mode).where(Mode.project_id == project_id).order_by(Mode.created_at.asc())
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def get_mode_by_name(self, project_id: int, name: str) -> Mode | None:
        stmt = select(Mode).where(Mode.project_id == project_id, Mode.name == name)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_mode_by_id(self, mode_id: int) -> Mode | None:
        stmt = select(Mode).where(Mode.id == mode_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def create_mode(
        self,
        project_id: int,
        name: str,
        system_prompt: str | None = None,
        tools_config: str | None = None,
        temperature: str | None = None,
    ) -> Mode:
        existing = await self.get_mode_by_name(project_id, name)
        if existing:
            raise ValueError("Mode with this name already exists in the project")
        # Repo-level guard for temperature
        norm_temp = _normalize_temperature(temperature) if temperature is not None else None
        md = Mode(
            project_id=project_id,
            name=name,
            system_prompt=system_prompt,
            tools_config=tools_config,
            temperature=norm_temp,
        )
        self.session.add(md)
        await self.session.commit()
        await self.session.refresh(md)
        return md

    async def update_mode(self, mode_id: int, **fields) -> Mode | None:
        md = await self.get_mode_by_id(mode_id)
        if not md:
            return None
        for k, v in fields.items():
            if hasattr(md, k) and v is not None:
                if k == "temperature":
                    v = _normalize_temperature(v)
                setattr(md, k, v)
        await self.session.commit()
        await self.session.refresh(md)
        return md

    async def delete_mode(self, mode_id: int) -> bool:
        md = await self.get_mode_by_id(mode_id)
        if not md:
            return False
        await self.session.delete(md)
        await self.session.commit()
        return True