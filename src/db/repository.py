# Файл: C:\desk_top\src\db\repository.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from src.db.models import User, Session

class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_user(self, telegram_id: int, username: str = None) -> User:
        """Получает пользователя по telegram_id или создает нового, если он не найден."""
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

class SessionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def start_new_session(self, user: User) -> Session:
        """Создает новую активную сессию для пользователя."""
        new_session = Session(user_id=user.telegram_id, status='active')
        self.session.add(new_session)
        await self.session.commit()
        await self.session.refresh(new_session)
        return new_session