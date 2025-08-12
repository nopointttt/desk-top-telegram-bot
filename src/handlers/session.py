import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repository import UserRepository, SessionRepository

router = Router()

@router.message(Command("start_session"))
async def cmd_start_session(message: Message, session: AsyncSession):
    """Handler for the /start_session command."""
    logging.info(f"User {message.from_user.id} starting a new session.")

    user_repo = UserRepository(session)
    session_repo = SessionRepository(session)

    # Find or create the user
    user = await user_repo.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username
    )

    # Create a new session for them in the DB
    new_db_session = await session_repo.start_new_session(user)

    await message.answer(
        f"New session #{new_db_session.id} started. What is the goal of this session and what result do you expect?"
    )