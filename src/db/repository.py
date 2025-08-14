# Файл: C:\desk_top\src\db\repository.py
import datetime
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from src.db.models import User, Session, PersonalizedPrompt

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
        await self.session.execute(
            delete(User).where(User.telegram_id == telegram_id)
        )
        await self.session.commit()
        logging.info(f"All data for user {telegram_id} has been deleted.")

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
        if session_obj and session_obj.message_history:
            history_val = session_obj.message_history
            if isinstance(history_val, str):
                session_obj.message_history = json.loads(history_val)
            elif isinstance(history_val, bytes):
                session_obj.message_history = json.loads(history_val.decode('utf-8'))
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

    async def start_new_session(self, user: User, profile: str) -> Session:
        await self.close_all_active_sessions(user.telegram_id)
        new_session = Session(
            user_id=user.telegram_id, 
            status='active', 
            active_profile=profile,
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

    async def list_sessions(self, user_id: int) -> list[Session]:
        stmt = select(Session).where(Session.user_id == user_id).order_by(Session.created_at.desc())
        result = await self.session.execute(stmt)
        sessions = result.scalars().all()
        return [self._deserialize_history(s) for s in sessions]

    # --- ФИНАЛЬНОЕ ИСПРАВЛЕНИЕ ---
    async def update_message_history(self, session_id: int, new_message: dict):
        active_session = await self.session.get(Session, session_id)
        if active_session:
            history_val = active_session.message_history
            
            # 1. Надежно получаем историю в виде списка, независимо от ее текущего типа
            if isinstance(history_val, list):
                history_list = history_val
            elif isinstance(history_val, str):
                history_list = json.loads(history_val or '[]')
            elif isinstance(history_val, bytes):
                 history_list = json.loads(history_val.decode('utf-8') or '[]')
            else:
                history_list = []

            # 2. Добавляем новое сообщение
            history_list.append(new_message)
            
            # 3. Сериализуем обратно в строку для записи в БД
            active_session.message_history = json.dumps(history_list, ensure_ascii=False)
            await self.session.commit()
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

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