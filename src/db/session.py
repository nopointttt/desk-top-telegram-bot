# Файл: C:\desk_top\src\db\session.py (Правильная версия)
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.db.models import Base
from src.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    """Инициализирует базу данных, создает таблицы."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Зависимость для получения сессии БД."""
    async with AsyncSessionLocal() as session:
        yield session