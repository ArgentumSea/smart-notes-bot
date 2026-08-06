"""APScheduler: проверка напоминаний каждую минуту."""

import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, and_

from database import async_session
from models import Reminder, Task, User
from callbacks import TaskActionCB, PostponeCB

logger = logging.getLogger(__name__)


async def send_reminder(bot: Bot, reminder: Reminder, task: Task, user: User) -> None:
    text = f"🔔 Напоминание!\n«{task.task_text}»"

    if reminder.reminder_type == "morning_digest":
        text = f"☀️ Доброе утро! Задача на сегодня:\n«{task.task_text}»"
        if task.deadline_dt:
            text += f"\n⏰ {task.deadline_dt.strftime('%H:%M')}"
    elif reminder.reminder_type == "one_hour_before":
        text = f"⏰ Через час задача:\n«{task.task_text}»"
    elif reminder.reminder_type == "exact_time":
        text = f"🔔 Сейчас выполнить:\n«{task.task_text}»"

    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Выполнено",
        callback_data=TaskActionCB(task_id=task.task_id, action="done", offset=0)
    )
    kb.button(
        text="⏸ Перенести",
        callback_data=PostponeCB(task_id=task.task_id, variant="menu")
    )

    try:
        await bot.send_message(user.chat_id, text, reply_markup=kb.as_markup())
    except TelegramForbiddenError:
        logger.warning(f"User blocked bot. Skipping reminder {reminder.reminder_id}")
    except TelegramRetryAfter as e:
        logger.warning(f"Rate limit hit. Retry after {e.retry_after}s")
        raise
    except Exception as e:
        logger.error(f"Failed to send reminder {reminder.reminder_id}: {type(e).__name__}")


async def check_reminders(bot: Bot) -> None:
    now = datetime.now()
    async with async_session() as db:
        result = await db.execute(
            select(Reminder, Task, User)
            .join(Task, Reminder.task_id == Task.task_id)
            .join(User, Task.user_id == User.user_id)
            .where(
                and_(
                    Reminder.is_sent == 0,
                    Reminder.scheduled_time <= now,
                    Task.is_completed == 0,
                )
            )
        )
        rows = result.all()

        for reminder, task, user in rows:
            try:
                await send_reminder(bot, reminder, task, user)
                reminder.is_sent = 1
                await db.commit()
            except TelegramRetryAfter:
                break
            except Exception as e:
                logger.error(f"Error in reminder {reminder.reminder_id}: {type(e).__name__}")
                reminder.is_sent = 1
                await db.commit()


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_reminders,
        trigger=IntervalTrigger(minutes=1),
        args=[bot],
        id="reminder_checker",
        replace_existing=True,
    )
    return scheduler
