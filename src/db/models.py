# Файл: C:\desk_top\src\db\models.py
from sqlalchemy import (
    Column, Integer, String, BigInteger,
    DateTime, Text, ForeignKey, func, Date, UniqueConstraint
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy_utils import StringEncryptedType
from src.config import ENCRYPTION_KEY

class CacheableEncryptedType(StringEncryptedType):
    cache_ok = True

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(BigInteger, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    tokens_used_today = Column(Integer, default=0, nullable=False)
    last_request_date = Column(Date, default=func.current_date(), nullable=False)
    
    # Каскадное удаление настраивается здесь, на стороне "один"
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    prompts = relationship("PersonalizedPrompt", back_populates="user", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")

class Project(Base):
    __tablename__ = 'projects'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False, index=True)
    name = Column(String, nullable=False)
    goal = Column(Text)
    context = Column(Text)
    active_mode = Column(String)
    system_prompt = Column(CacheableEncryptedType(Text, ENCRYPTION_KEY))
    backlog = Column(CacheableEncryptedType(Text, ENCRYPTION_KEY))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uq_project_user_name'),
    )

    user = relationship("User", back_populates="projects")
    sessions = relationship("Session", back_populates="project", cascade="all, delete-orphan")
    modes = relationship("Mode", back_populates="project", cascade="all, delete-orphan")

class Mode(Base):
    __tablename__ = 'modes'
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False, index=True)
    # Человекочитаемое имя (например: 'coder', 'product_manager', 'assistant')
    name = Column(String, nullable=False)
    # Переопределение системного промпта на уровне мода (если None — использовать проектный)
    system_prompt = Column(CacheableEncryptedType(Text, ENCRYPTION_KEY))
    # Конфигурация инструментов/политик (JSON-текст, шифруется)
    tools_config = Column(CacheableEncryptedType(Text, ENCRYPTION_KEY))
    # Параметры инференса (например, температура)
    temperature = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('project_id', 'name', name='uq_mode_project_name'),
    )

    project = relationship("Project", back_populates="modes")

class Session(Base):
    __tablename__ = 'sessions'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=True, index=True)
    mode_id = Column(Integer, ForeignKey('modes.id'), nullable=True, index=True)
    status = Column(String, default='active', nullable=False)
    active_profile = Column(String)
    initial_goal = Column(Text)
    final_summary_id = Column(String)
    message_history = Column(CacheableEncryptedType(Text, ENCRYPTION_KEY))
    thinking_log = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True))
    # Режим выбора контекста: 'project' | 'acl_mentions' | 'global'
    context_mode = Column(String, default='project', nullable=False)
    
    # --- ИСПРАВЛЕНИЕ: Убираем некорректный cascade ---
    user = relationship("User", back_populates="sessions")
    project = relationship("Project", back_populates="sessions")
    mode = relationship("Mode")

class PersonalizedPrompt(Base):
    __tablename__ = 'personalized_prompts'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    profile = Column(String, nullable=False)
    prompt_text = Column(CacheableEncryptedType(Text, ENCRYPTION_KEY), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # --- ИСПРАВЛЕНИЕ: Убираем некорректный cascade ---
    user = relationship("User", back_populates="prompts")

class ProjectAccess(Base):
    __tablename__ = 'project_access'
    id = Column(Integer, primary_key=True, index=True)
    # Проект-владелец (контекст которого может подтягивать другие проекты)
    owner_project_id = Column(Integer, ForeignKey('projects.id'), nullable=False, index=True)
    # Проект, к которому разрешён доступ (можно подтаскивать его контент)
    allowed_project_id = Column(Integer, ForeignKey('projects.id'), nullable=False, index=True)
    # Область прав (например: 'read', 'summaries', 'all') — на будущее
    scope = Column(String, default='read', nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('owner_project_id', 'allowed_project_id', name='uq_owner_allowed'),
    )