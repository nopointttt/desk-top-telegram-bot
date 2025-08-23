# Файл: C:\desk_top\src\handlers\session.py
import logging
import json
import asyncio
import re  # <-- 1. Импортируем модуль для регулярных выражений
import unicodedata
from aiogram import Router, F, Bot
from aiogram.enums import ChatAction
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command, StateFilter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.db.models import Mode
from src.db.repository import (
    UserRepository,
    SessionRepository,
    PersonalizedPromptRepository,
    ProjectRepository,
    ProjectAccessRepository,
)
from src.services.llm_client import LLMClient
from src.services.rag_client import RAGClient
from src.services.prompt_builder import build_prompt

router = Router()
logger = logging.getLogger(__name__)

profile_choice_keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Кодер"), KeyboardButton(text="Продакт менеджер")], [KeyboardButton(text="Личный ассистент")]], resize_keyboard=True, one_time_keyboard=True)

# --- 2. Новая функция для очистки HTML ---
def clean_html(raw_html: str) -> str:
    """Надежно удаляет все HTML-теги из строки."""
    if not isinstance(raw_html, str):
        return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext

# --- Нормализация имён проектов для устойчивого сравнения ---
def _norm(s: str) -> str:
    """Unicode NFKC + casefold + trim для сравнения имён (не меняет исходные).
    Совместимо с handlers/acl.py._norm.
    """
    return unicodedata.normalize("NFKC", (s or "").strip()).casefold()

# --- Безопасное редактирование: если нельзя отредактировать, отправляем новое сообщение ---
async def safe_edit_or_send(bot: Bot, status_message: Message, text: str):
    try:
        await status_message.edit_text(text)
    except Exception:
        await bot.send_message(chat_id=status_message.chat.id, text=text)

# --- ОБРАБОТЧИКИ КОМАНД (без изменений) ---
@router.message(Command("start_session"))
async def cmd_start_session(message: Message):
    await message.answer("С каким профилем начать сессию?", reply_markup=profile_choice_keyboard)

@router.message(F.text.in_({"Кодер", "Продакт менеджер", "Личный ассистент"}))
async def process_profile_choice(message: Message, session: AsyncSession):
    profile_map = { "Кодер": "coder", "Продакт менеджер": "product_manager", "Личный ассистент": "personal_assistant" }
    profile = profile_map.get(message.text)
    user_repo = UserRepository(session)
    session_repo = SessionRepository(session)
    user = await user_repo.get_or_create_user(telegram_id=message.from_user.id, username=message.from_user.username)
    new_db_session = await session_repo.start_new_session(user, profile)
    logger.info(f"ANALYTICS - Event: SessionStarted, UserID: {message.from_user.id}, Details: {{'session_id': {new_db_session.id}, 'profile': '{profile}'}}")
    await message.answer(f"Новая сессия #{new_db_session.id} с профилем '{message.text}' начата. Что будем делать?", reply_markup=ReplyKeyboardRemove())

@router.message(Command("end_session"))
async def cmd_end_session(message: Message, session: AsyncSession, llm_client: LLMClient, rag_client: RAGClient):
    repo = SessionRepository(session)
    active_session = await repo.get_active_session(message.from_user.id)
    if not active_session:
        await message.answer("У вас нет активных сессий.")
        return
    await message.answer("Подвожу итоги сессии...")
    history = active_session.message_history
    if history:
        summary = await llm_client.get_summary(history)
        await rag_client.save_summary(
            active_session.id,
            message.from_user.id,
            summary,
            project_id=active_session.project_id,
        )
    logger.info(f"ANALYTICS - Event: SessionEnded, UserID: {message.from_user.id}, Details: {{'session_id': {active_session.id}}}")
    await repo.close_all_active_sessions(message.from_user.id)
    await message.answer(f"Сессия #{active_session.id} завершена. Итоги сохранены.")

@router.message(Command("list_sessions"))
async def cmd_list_sessions(message: Message, session: AsyncSession):
    repo = SessionRepository(session)
    user_sessions = await repo.list_sessions(message.from_user.id)
    if not user_sessions:
        await message.answer("У вас еще нет ни одной сессии.")
        return
    response_text = "Ваши сессии:\n\n"
    for s in user_sessions:
        status_emoji = "🟢" if s.status == 'active' else "🔴"
        response_text += f"{status_emoji} Сессия #{s.id} от {s.created_at.strftime('%Y-%m-%d %H:%M')}\n"
    await message.answer(response_text)

@router.message(Command("current"))
async def cmd_current(message: Message, session: AsyncSession):
    """Показывает активную сессию и проект (если есть)."""
    sess_repo = SessionRepository(session)
    proj_repo = ProjectRepository(session)

    active = await sess_repo.get_active_session(message.from_user.id)
    if not active:
        await message.answer(
            "Активной сессии нет. Используйте /start_session для начала или /projects для выбора проекта."
        )
        return

    project_part = "без проекта"
    mode_part = "mode=n/a"
    ctx_part = "ctx=project"
    if active.project_id:
        project = await proj_repo.get_project_by_id(active.project_id)
        if project:
            project_part = f"проект: {project.name} (id={project.id})"
    # Дополнительно: покажем активный Mode из сессии
    try:
        m_id = getattr(active, 'mode_id', None)
        if m_id:
            res = await session.execute(select(Mode).where(Mode.id == m_id))
            m = res.scalar_one_or_none()
            if m:
                temp_display = f", t={m.temperature}" if getattr(m, 'temperature', None) not in (None, "") else ""
                mode_part = f"mode: {m.name}{temp_display}"
    except Exception:
        pass

    # Текущий режим контекста
    try:
        ctx = await sess_repo.get_context_mode(message.from_user.id)
        if ctx:
            ctx_part = f"ctx={ctx}"
    except Exception:
        pass

    text = (
        f"Текущая сессия #{active.id} (профиль: {active.active_profile or 'n/a'}, {project_part}, {mode_part}, {ctx_part}).\n"
        f"Создана: {active.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"Подсказка: можно ссылаться на другие проекты через @[ProjectName]."
    )
    await message.answer(text)


@router.message(Command("pin_status"))
async def pin_status(message: Message, session: AsyncSession, bot: Bot):
    """Отправляет и пытается закрепить баннер статуса (текущий проект/режим/сессия)."""
    user_repo = UserRepository(session)
    sess_repo = SessionRepository(session)
    proj_repo = ProjectRepository(session)

    user = await user_repo.get_or_create_user(message.from_user.id, message.from_user.username)
    active = await sess_repo.get_active_session(user.telegram_id)
    if not active:
        await message.answer("Нет активной сессии. Используйте /start_session или /projects.")
        return
    project_part = "без проекта"
    mode_part = "mode=n/a"
    if active.project_id:
        project = await proj_repo.get_project_by_id(active.project_id)
        if project:
            project_part = f"проект: {project.name} (id={project.id})"
    # Дополнительно: Mode из сессии
    try:
        m_id = getattr(active, 'mode_id', None)
        if m_id:
            res = await session.execute(select(Mode).where(Mode.id == m_id))
            m = res.scalar_one_or_none()
            if m:
                temp_display = f", t={m.temperature}" if getattr(m, 'temperature', None) not in (None, "") else ""
                mode_part = f"mode: {m.name}{temp_display}"
    except Exception:
        pass

    # Текущий режим контекста
    try:
        ctx = await sess_repo.get_context_mode(user.telegram_id)
        if ctx:
            ctx_part = f"ctx={ctx}"
    except Exception:
        pass

    banner = (
        f"📌 Статус: сессия #{active.id} (профиль: {active.active_profile or 'n/a'}, {project_part}, {mode_part}, {ctx_part}).\n"
        f"Создана: {active.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"Подсказка: /projects для переключения, @[ProjectName] для межпроектного контекста."
    )
    sent = await message.answer(banner)
    try:
        await bot.pin_chat_message(chat_id=sent.chat.id, message_id=sent.message_id, disable_notification=True)
    except Exception:
        # Нет прав или закрепление запрещено — просто оставляем сообщение
        pass

# --- ОБЩИЙ ОБРАБОТЧИК ТЕКСТА (исключаем команды и любые активные FSM состояния) ---
@router.message(F.content_type.in_({'text'}), ~F.text.regexp(r'^/'), StateFilter(None))
async def handle_text_message(message: Message, session: AsyncSession, bot: Bot, llm_client: LLMClient, rag_client: RAGClient):
    user_id = message.from_user.id
    user_repo = UserRepository(session)
    session_repo = SessionRepository(session)
    project_repo = ProjectRepository(session)
    
    user = await user_repo.get_or_create_user(user_id, message.from_user.username)
    request_tokens = llm_client.count_tokens(message.text)
    if not await user_repo.check_and_update_limits(user, request_tokens):
        await message.answer("Вы превысили суточный лимит использования токенов. Попробуйте снова завтра.")
        return

    active_session = await session_repo.get_active_session(user_id)
    if not active_session:
        # Неблокирующий режим: пробуем ответить эпизодически без сохранения истории.
        # 1) Предложим быстрые действия
        quick_actions = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="/start_session"), KeyboardButton(text="/new_project")],
                [KeyboardButton(text="/projects")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

        status_message = await message.answer(
            "<i>Нет активной сессии — отвечу без сохранения контекста.\n"
            "Можете запустить /start_session или создать проект.</i>",
            reply_markup=quick_actions,
        )

        try:
            # Выберем системный промпт по умолчанию (профиль 'coder')
            prompt_repo = PersonalizedPromptRepository(session)
            system_prompt = await prompt_repo.get_prompt(user_id, "coder")
            if not system_prompt:
                await safe_edit_or_send(bot, status_message, "Профиль по умолчанию не настроен. Откройте /personalize или /start_session")
                return

            # Истории нет, ответ будет одноразовым
            history: list[dict] = []

            # Эфемерный режим: строгая изоляция — без межпроектного доступа.
            await safe_edit_or_send(bot, status_message, "<i>Анализирую запрос...\nИщу релевантную информацию в долгосрочной памяти...</i>")
            relevant_summaries = await rag_client.find_relevant_summaries(user_id, message.text, project_id=None)
            cross_info = ""
            await safe_edit_or_send(bot, status_message, (
                f"<i>Анализирую запрос...\nИщу релевантную информацию в долгосрочной памяти... ✓\n"
                f"Найдено {len(relevant_summaries)} итогов{cross_info}.\nФормирую запрос к AI...</i>"
            ))

            response_text_raw = await llm_client.get_response(
                system_prompt, history, message.text, rag_context=relevant_summaries
            )
            response_text = clean_html(response_text_raw)

            response_tokens = llm_client.count_tokens(response_text)
            await user_repo.check_and_update_limits(user, response_tokens)

            await safe_edit_or_send(bot, status_message, response_text + "\n\n--- \n<i>Эфемерный ответ (без активной сессии). Используйте /start_session для контекстного диалога.</i>")
        except Exception as e:
            logger.error(f"Error in ephemeral handle_text_message: {e}", exc_info=True)
            await safe_edit_or_send(bot, status_message, "Произошла непредвиденная ошибка.")
        return

    status_message = await message.answer("<i>Анализирую запрос...</i>")
    try:
        # 1) Определяем активный проект и строим system_prompt через Prompt Builder
        active_project = None
        if active_session.project_id:
            active_project = await project_repo.get_project_by_id(active_session.project_id)

        try:
            system_prompt, mode_temperature = await build_prompt(session, user_id, active_session, active_project)
        except ValueError as e:
            await safe_edit_or_send(bot, status_message, str(e))
            return

        history = active_session.message_history

        # 2) RAG по режиму контекста: 'project' | 'acl_mentions' | 'global'
        await safe_edit_or_send(bot, status_message, "<i>Анализирую запрос...\nИщу релевантную информацию в долгосрочной памяти...</i>")
        session_repo = SessionRepository(session)
        context_mode = await session_repo.get_context_mode(user_id)

        relevant_summaries: list[str] = []
        cross_info = ""

        if context_mode == 'global':
            # Полностью глобальный поиск без проектного фильтра
            relevant_summaries = await rag_client.find_relevant_summaries(
                user_id, message.text, project_id=None, project_ids=None
            )
        elif context_mode == 'project':
            # Только текущий проект (если он задан), иначе глобально
            pid = active_project.id if active_project else None
            relevant_summaries = await rag_client.find_relevant_summaries(
                user_id, message.text, project_id=pid, project_ids=None
            )
        else:
            # acl_mentions: текущий проект + упомянутые @[Project] по ACL
            project_ids: list[int] = []
            if not active_project:
                # Жёсткая изоляция: без активного проекта acl_mentions не выполняет RAG
                relevant_summaries = []
                cross_info = " | acl_mentions: нет активного проекта"
            else:
                project_ids.append(active_project.id)

                mentions = re.findall(r"@\[([^\]]+)\]", message.text or "")
                unique_mentions: list[str] = []
                for name in mentions:
                    n = name.strip()
                    if n and n not in unique_mentions:
                        unique_mentions.append(n)

                ignored_missing: list[str] = []   # не найден проект у пользователя
                ignored_denied: list[str] = []    # нет ACL-доступа

                if unique_mentions:
                    acl_repo = ProjectAccessRepository(session)
                    # Предзагрузим список проектов пользователя для нормализованного поиска
                    user_projects = await project_repo.list_projects(user_id)
                    for proj_name in unique_mentions:
                        # 1) Пытаемся точным именем
                        other_proj = await project_repo.get_project_by_name(user_id, proj_name)
                        # 2) Если не нашли — пробуем нормализованное сравнение среди проектов пользователя
                        if not other_proj and user_projects:
                            target_norm = _norm(proj_name)
                            for p in user_projects:
                                if _norm(getattr(p, 'name', '')) == target_norm:
                                    other_proj = p
                                    break
                        if not other_proj:
                            ignored_missing.append(proj_name)
                            continue
                        if await acl_repo.is_allowed(active_project.id, other_proj.id):
                            project_ids.append(other_proj.id)
                        else:
                            ignored_denied.append(proj_name)

                relevant_summaries = await rag_client.find_relevant_summaries(
                    user_id, message.text,
                    project_id=None if project_ids else (active_project.id if active_project else None),
                    project_ids=project_ids if project_ids else None,
                )

                if project_ids and len(project_ids) > 1:
                    cross_info = f" (+{len(project_ids)-1} проектов по ACL)"
                # Добавим обратную связь по проигнорированным упоминаниям (без раскрытия контента)
                ignored_parts = []
                if ignored_missing:
                    ignored_parts.append(f"нет таких проектов: {', '.join(ignored_missing)}")
                if ignored_denied:
                    ignored_parts.append(f"нет доступа: {', '.join(ignored_denied)}")
                if ignored_parts:
                    suffix = "; ".join(ignored_parts)
                    cross_info += f" | игнор: {suffix}"
        log_text = (
            f"<i>Анализирую запрос...\n"
            f"Ищу релевантную информацию в долгосрочной памяти... ✓\n"
            f"Найдено {len(relevant_summaries)} итогов{cross_info}.\n"
            f"Формирую запрос к AI...</i>"
        )
        await safe_edit_or_send(bot, status_message, log_text)

        response_text_raw = await llm_client.get_response(
            system_prompt, history, message.text, rag_context=relevant_summaries, temperature=mode_temperature
        )

        # --- 3. ПРИМЕНЯЕМ ОЧИСТКУ ---
        response_text = clean_html(response_text_raw)

        response_tokens = llm_client.count_tokens(response_text)
        await user_repo.check_and_update_limits(user, response_tokens)

        current_history_text = " ".join([msg['content'] for msg in history])
        token_count = llm_client.count_tokens(current_history_text)
        CONTEXT_WINDOW = 16000 
        response_with_context = (
            f"{response_text}\n\n"
            f"--- \n"
            f"<i>Контекст сессии: {token_count} / {CONTEXT_WINDOW} токенов</i>"
        )
        
        await safe_edit_or_send(bot, status_message, response_with_context)
        
        await session_repo.update_message_history(active_session.id, {"role": "user", "content": message.text})
        await session_repo.update_message_history(active_session.id, {"role": "assistant", "content": response_text})
    except Exception as e:
        logger.error(f"Error in handle_text_message: {e}", exc_info=True)
        await safe_edit_or_send(bot, status_message, "Произошла непредвиденная ошибка.")