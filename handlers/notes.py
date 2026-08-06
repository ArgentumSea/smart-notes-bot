"""Хендлеры приёма заметок: текст, голос, forward."""

import os
import tempfile
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters.command import Command
from aiogram.filters.state import StateFilter

from database import async_session
from models import User
from sqlalchemy import select
from config import ADMIN_USER_ID
from note_processor import process_note, format_response
from voice_recognizer import recognize_ogg

logger = logging.getLogger(__name__)
router = Router()

MAX_NOTE_LENGTH = 10000


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    lines = [
        "👋 Привет! Я бот для умных заметок.\n",
        "📝 Просто напиши мне — я сохраню и сделаю краткое содержание.",
        "🎙 Можешь прислать голосовое — распознаю текст и покажу его.",
        "↩️ Пересылай сообщения из других чатов.\n",
        "⚙️ Команды:",
        "/tasks — мои задачи",
        "/today — план на сегодня",
        "/cancel — отменить текущее действие",
    ]
    if message.from_user.id == ADMIN_USER_ID:
        lines.append("/admin — управление пользователями")
    await message.answer("\n".join(lines))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📖 Справка по боту\n\n"
        "📝 Заметки:\n"
        "• Отправь текст — сохраню и сделаю summary\n"
        "• Голосовое — распознаю и обработаю\n"
        "• Пересланное сообщение — сохраню\n\n"
        "✅ Задачи:\n"
        "• /tasks — список задач с пагинацией\n"
        "• /today — задачи на сегодня\n"
        "• Нажми на номер задачи — измени дедлайн или отметь выполненной\n\n"
        "⏰ Напоминания:\n"
        "• Утром в 10:00 — сводка на день\n"
        "• За час до дедлайна\n"
        "• В точное время дедлайна\n\n"
        "⚙️ /cancel — отменить текущее действие"
    )


@router.message(F.text & ~F.text.startswith("/"), StateFilter(None))
async def handle_text(message: Message) -> None:
    async with async_session() as db:
        result = await db.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if user and user.is_blocked:
            await message.answer("🚫 Доступ заблокирован.")
            return
    if len(message.text) > MAX_NOTE_LENGTH:
        await message.answer(f"❌ Слишком длинное сообщение. Максимум {MAX_NOTE_LENGTH} символов.")
        return

    status = await message.answer("⏳ Обрабатываю заметку...")
    try:
        async with async_session() as db:
            result = await process_note(
                db=db,
                user_id=message.from_user.id,
                chat_id=message.chat.id,
                text=message.text,
                source_type="text",
            )
            await status.edit_text(format_response(result))
    except Exception as e:
        logger.error(f"Error processing text: {type(e).__name__}: {e}")
        await status.edit_text("❌ Произошла ошибка при обработке заметки. Попробуйте ещё раз.")


@router.message(F.voice, StateFilter(None))
async def handle_voice(message: Message, bot: Bot) -> None:
    async with async_session() as db:
        result = await db.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if user and user.is_blocked:
            await message.answer("🚫 Доступ заблокирован.")
            return
    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    ogg_path = tmp.name
    tmp.close()

    status = await message.answer("🎙 Слушаю...")

    try:
        logger.info(f"Downloading voice to {ogg_path}")
        await bot.download(message.voice, destination=ogg_path)
        file_size = os.path.getsize(ogg_path)
        logger.info(f"Voice downloaded: {file_size} bytes")

        await status.edit_text("📝 Распознаю речь...")

        try:
            recognized = recognize_ogg(ogg_path)
        except RuntimeError as e:
            logger.error(f"Voice recognition error: {e}")
            await status.edit_text("🎙 Ошибка распознавания речи.")
            return

        logger.info(f"Voice recognized: '{recognized}'")

        if not recognized:
            await status.edit_text("🎙 Не удалось распознать речь. Попробуйте говорить громче и чётче.")
            return

        await status.edit_text(f"🎙 Распознано:\n«{recognized}»\n\n⏳ Обрабатываю...")

        if len(recognized) > MAX_NOTE_LENGTH:
            await status.edit_text(f"❌ Слишком длинное сообщение. Максимум {MAX_NOTE_LENGTH} символов.")
            return

        async with async_session() as db:
            result = await process_note(
                db=db,
                user_id=message.from_user.id,
                chat_id=message.chat.id,
                text=recognized,
                source_type="voice",
            )
            await status.edit_text(format_response(result))

    except Exception as e:
        logger.error(f"Error processing voice: {type(e).__name__}: {e}")
        try:
            await status.edit_text("❌ Произошла ошибка при обработке голосового. Попробуйте ещё раз.")
        except Exception:
            await message.answer("❌ Произошла ошибка при обработке голосового. Попробуйте ещё раз.")

    finally:
        try:
            if os.path.exists(ogg_path):
                os.remove(ogg_path)
        except OSError:
            pass


@router.message(F.forward_from | F.forward_sender_name, StateFilter(None))
async def handle_forward(message: Message) -> None:
    async with async_session() as db:
        result = await db.execute(select(User).where(User.user_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if user and user.is_blocked:
            await message.answer("🚫 Доступ заблокирован.")
            return
    text = message.text or message.caption or ""
    if not text:
        await message.answer("↩️ Пересланное сообщение без текста — не могу сохранить.")
        return
    if len(text) > MAX_NOTE_LENGTH:
        await message.answer(f"❌ Слишком длинное сообщение. Максимум {MAX_NOTE_LENGTH} символов.")
        return

    status = await message.answer("⏳ Обрабатываю заметку...")
    try:
        async with async_session() as db:
            result = await process_note(
                db=db,
                user_id=message.from_user.id,
                chat_id=message.chat.id,
                text=text,
                source_type="forward",
            )
            await status.edit_text(format_response(result))
    except Exception as e:
        logger.error(f"Error processing forward: {type(e).__name__}: {e}")
        await status.edit_text("❌ Произошла ошибка при обработке заметки. Попробуйте ещё раз.")
