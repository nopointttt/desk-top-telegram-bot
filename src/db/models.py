# Файл: C:\desk_top\src\db\models.py
from sqlalchemy import (
    Column, Integer, String, BigInteger,
    DateTime, Text, ForeignKey, func 
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy_utils import EncryptedType
from src.config import ENCRYPTION_KEY

class CacheableEncryptedType(EncryptedType):
    cache_ok = True

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(BigInteger, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sessions = relationship("Session", back_populates="user")
    prompts = relationship("PersonalizedPrompt", back_populates="user")

class Session(Base):
    __tablename__ = 'sessions'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    status = Column(String, default='active', nullable=False)
    active_profile = Column(String)
    initial_goal = Column(Text)
    final_summary_id = Column(String)
    # --- ВОЗВРАЩАЕМ Text. Мы будем управлять JSON вручную в репозитории ---
    message_history = Column(CacheableEncryptedType(Text, ENCRYPTION_KEY))
    thinking_log = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True))
    user = relationship("User", back_populates="sessions")

class PersonalizedPrompt(Base):
    __tablename__ = 'personalized_prompts'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    profile = Column(String, nullable=False)
    prompt_text = Column(CacheableEncryptedType(Text, ENCRYPTION_KEY), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="prompts")