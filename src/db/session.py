# Файл: C:\desk_top\src\db\session.py
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.db.models import Base
from src.config import DATABASE_URL

# Создаем "контейнер" для хранения подключения
class Database:
    def __init__(self):
        self.engine = None
        self.AsyncSessionLocal = None

db = Database()

async def db_init():
    """Асинхронно инициализирует движок и фабрику сессий."""
    db.engine = create_async_engine(DATABASE_URL, echo=False)
    db.AsyncSessionLocal = sessionmaker(
        bind=db.engine, class_=AsyncSession, expire_on_commit=False
    )
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Зависимость для получения сессии БД."""
    async with db.AsyncSessionLocal() as session:
        yield session