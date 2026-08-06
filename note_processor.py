"""Сервисный слой обработки заметок."""

import logging
import re
from datetime import datetime, time
from typing import Optional

import dateparser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gemini_rotator import GeminiRotator
from models import User, Note, Task
from services.reminders import create_reminders_for_task
from config import TZ

logger = logging.getLogger(__name__)
rotator = GeminiRotator()

_TIME_REPLACEMENTS = [
    (r'\bв\s+(\d{1,2})\b(?!\s*[\d:])', r'в \1:00'),
    (r'\bв\s+полдень\b', 'в 12:00'),
    (r'\bв\s+полночь\b', 'в 00:00'),
    (r'\bв\s+час\s+дня\b', 'в 13:00'),
    (r'\bв\s+два\s+часа\s+дня\b', 'в 14:00'),
    (r'\bв\s+три\s+часа\s+дня\b', 'в 15:00'),
    (r'\bв\s+четыре\s+часа\s+дня\b', 'в 16:00'),
    (r'\bв\s+пять\s+часов\s+дня\b', 'в 17:00'),
    (r'\bв\s+шесть\s+часов\s+дня\b', 'в 18:00'),
    (r'\bв\s+семь\s+часов\s+дня\b', 'в 19:00'),
    (r'\bв\s+восемь\s+часов\s+дня\b', 'в 20:00'),
    (r'\bв\s+девять\s+часов\s+дня\b', 'в 21:00'),
    (r'\bв\s+десять\s+часов\s+дня\b', 'в 22:00'),
    (r'\bв\s+одиннадцать\s+часов\s+дня\b', 'в 23:00'),
    (r'\bв\s+двенадцать\s+часов\s+дня\b', 'в 12:00'),
    (r'\bв\s+час\s+ночи\b', 'в 01:00'),
    (r'\bв\s+два\s+часа\s+ночи\b', 'в 02:00'),
    (r'\bв\s+три\s+часа\s+ночи\b', 'в 03:00'),
    (r'\bв\s+четыре\s+часа\s+ночи\b', 'в 04:00'),
    (r'\bв\s+пять\s+часов\s+ночи\b', 'в 05:00'),
    (r'\bв\s+шесть\s+часов\s+ночи\b', 'в 06:00'),
    (r'\bв\s+час\s+утра\b', 'в 01:00'),
    (r'\bв\s+два\s+часа\s+утра\b', 'в 02:00'),
    (r'\bв\s+три\s+часа\s+утра\b', 'в 03:00'),
    (r'\bв\s+четыре\s+часа\s+утра\b', 'в 04:00'),
    (r'\bв\s+пять\s+часов\s+утра\b', 'в 05:00'),
    (r'\bв\s+шесть\s+часов\s+утра\b', 'в 06:00'),
    (r'\bв\s+семь\s+часов\s+утра\b', 'в 07:00'),
    (r'\bв\s+восемь\s+часов\s+утра\b', 'в 08:00'),
    (r'\bв\s+девять\s+часов\s+утра\b', 'в 09:00'),
    (r'\bв\s+десять\s+часов\s+утра\b', 'в 10:00'),
    (r'\bв\s+одиннадцать\s+часов\s+утра\b', 'в 11:00'),
    (r'\bв\s+двенадцать\s+часов\s+утра\b', 'в 12:00'),
    (r'\bв\s+час\s+вечера\b', 'в 13:00'),
    (r'\bв\s+два\s+часа\s+вечера\b', 'в 14:00'),
    (r'\bв\s+три\s+часа\s+вечера\b', 'в 15:00'),
    (r'\bв\s+четыре\s+часа\s+вечера\b', 'в 16:00'),
    (r'\bв\s+пять\s+часов\s+вечера\b', 'в 17:00'),
    (r'\bв\s+шесть\s+часов\s+вечера\b', 'в 18:00'),
    (r'\bв\s+семь\s+часов\s+вечера\b', 'в 19:00'),
    (r'\bв\s+восемь\s+часов\s+вечера\b', 'в 20:00'),
    (r'\bв\s+девять\s+часов\s+вечера\b', 'в 21:00'),
    (r'\bв\s+десять\s+часов\s+вечера\b', 'в 22:00'),
    (r'\bв\s+одиннадцать\s+часов\s+вечера\b', 'в 23:00'),
    (r'\bв\s+час\b', 'в 13:00'),
]


def _preprocess_time(text: str) -> str:
    result = text.lower()
    for pattern, replacement in _TIME_REPLACEMENTS:
        result = re.sub(pattern, replacement, result)
    return result


def _format_deadline(dt: Optional[datetime]) -> str:
    """Форматирует дедлайн: если время 00:00 — показывает только дату."""
    if not dt:
        return "без дедлайна"
    if dt.time() == time(0, 0):
        return dt.strftime("%d.%m.%Y")
    return dt.strftime("%d.%m.%Y %H:%M")


async def ensure_user(db: AsyncSession, user_id: int, chat_id: int) -> User:
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(user_id=user_id, chat_id=chat_id)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


def parse_deadline(text: str) -> Optional[datetime]:
    if not text:
        return None
    processed = _preprocess_time(text)
    logger.info(f"Date parse: '{text}' -> '{processed}'")
    dt = dateparser.parse(
        processed,
        languages=["ru"],
        settings={
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": False,
            "TIMEZONE": str(TZ),
            "TO_TIMEZONE": str(TZ),
        },
    )
    return dt


async def process_note(db: AsyncSession, user_id: int, chat_id: int, text: str, source_type: str) -> dict:
    user = await ensure_user(db, user_id, chat_id)
    ai_result = await rotator.process_note(text)

    note = Note(
        user_id=user.user_id,
        content=text,
        source_type=source_type,
        summary=ai_result.get("summary", ""),
    )
    db.add(note)
    await db.flush()

    tasks_data = []
    for item in ai_result.get("action_items", []):
        task_text = item.get("task", "")
        deadline_str = item.get("deadline")
        deadline_dt: Optional[datetime] = None

        if deadline_str and str(deadline_str).lower() not in ("null", "none", ""):
            try:
                deadline_dt = datetime.fromisoformat(str(deadline_str).replace("Z", "+00:00"))
                if deadline_dt.tzinfo is not None:
                    from zoneinfo import ZoneInfo
                    deadline_dt = deadline_dt.astimezone(ZoneInfo(str(TZ)))
                    deadline_dt = deadline_dt.replace(tzinfo=None)
            except ValueError:
                deadline_dt = parse_deadline(str(deadline_str))

        task = Task(
            note_id=note.note_id,
            user_id=user.user_id,
            task_text=task_text,
            deadline_dt=deadline_dt,
        )
        db.add(task)
        await db.flush()

        reminders = create_reminders_for_task(task)
        for r in reminders:
            db.add(r)

        tasks_data.append({
            "task_id": task.task_id,
            "text": task_text,
            "deadline": _format_deadline(deadline_dt),
            "reminders": [r.reminder_type for r in reminders],
        })

    await db.commit()
    return {"note_id": note.note_id, "summary": note.summary, "tasks": tasks_data}


def format_response(result: dict) -> str:
    lines = ["✅ Заметка сохранена!"]
    if result.get("summary"):
        lines.append(f"\n📋 Кратко: {result['summary']}")
    if result.get("tasks"):
        lines.append("\n✅ Задачи:")
        for i, t in enumerate(result["tasks"], 1):
            dl = t["deadline"]
            rem = ""
            if t["reminders"]:
                rem_map = {"exact_time": "в точное время", "one_hour_before": "за час", "morning_digest": "утром в 10:00"}
                rem = " → ⏰ " + ", ".join(rem_map.get(r, r) for r in t["reminders"])
            lines.append(f"{i}. «{t['text']}» → {dl}{rem}")
    return "\n".join(lines)
