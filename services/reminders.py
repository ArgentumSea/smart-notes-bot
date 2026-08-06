"""Логика создания и обновления напоминаний."""

from datetime import datetime, timedelta, time
from typing import Optional

from sqlalchemy import select, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from config import TZ
from models import Task, Reminder


def create_reminders_for_task(task: Task) -> list[Reminder]:
    reminders = []
    if not task.deadline_dt:
        return reminders

    dl: datetime = task.deadline_dt
    now = datetime.now()

    # Если время 00:00 — считаем что время не задано, напоминаем только утром
    time_not_set = (dl.time() == time(0, 0))

    if not time_not_set:
        # 1. Точное время дедлайна
        reminders.append(Reminder(
            task_id=task.task_id,
            reminder_type="exact_time",
            scheduled_time=dl,
        ))

        # 2. За час до (если ещё в будущем)
        hour_before = dl - timedelta(hours=1)
        if hour_before > now:
            reminders.append(Reminder(
                task_id=task.task_id,
                reminder_type="one_hour_before",
                scheduled_time=hour_before,
            ))

    # 3. Утренняя сводка в 10:00 (в день дедлайна)
    morning = datetime.combine(dl.date(), time(10, 0))
    if dl.time() >= time(10, 0) or time_not_set:
        if morning > now:
            reminders.append(Reminder(
                task_id=task.task_id,
                reminder_type="morning_digest",
                scheduled_time=morning,
            ))

    return reminders


async def update_task_deadline(db: AsyncSession, task_id: int, new_dt: Optional[datetime]) -> None:
    await db.execute(
        update(Task).where(Task.task_id == task_id).values(deadline_dt=new_dt)
    )
    await db.execute(
        delete(Reminder).where(
            and_(Reminder.task_id == task_id, Reminder.is_sent == 0)
        )
    )
    result = await db.execute(
        select(Task).where(Task.task_id == task_id)
    )
    task = result.scalar_one()
    for r in create_reminders_for_task(task):
        db.add(r)
    await db.commit()
