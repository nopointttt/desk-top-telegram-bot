# Файл: C:\desk_top\src\db\models.py
from sqlalchemy import (
    create_engine, Column, Integer, String, BigInteger,
    DateTime, Text, ForeignKey, func
)
from sqlalchemy.orm import relationship, declarative_base

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
    status = Column(String, default='active', nullable=False) # active, closed
    active_profile = Column(String) # coder, product_manager, personal_assistant
    initial_goal = Column(Text)
    final_summary_id = Column(String) # ID из Pinecone
    message_history = Column(Text)
    thinking_log = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True))
    
    user = relationship("User", back_populates="sessions")

class PersonalizedPrompt(Base):
    __tablename__ = 'personalized_prompts'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    profile = Column(String, nullable=False) # coder, product_manager, etc.
    prompt_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="prompts")