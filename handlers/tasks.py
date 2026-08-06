"""Хендлеры управления задачами."""

import logging
from datetime import datetime, timedelta, time

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters.command import Command
from aiogram.filters.state import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, update, delete, and_

from database import async_session
from models import Task, Reminder
from callbacks import TaskSelectCB, TaskActionCB, TaskConfirmCB, PostponeCB
from services.reminders import update_task_deadline
from note_processor import parse_deadline, _format_deadline

logger = logging.getLogger(__name__)
router = Router()


class EditTaskSG(StatesGroup):
    waiting_datetime = State()


class PostponeSG(StatesGroup):
    waiting_custom = State()


TASKS_PER_PAGE = 10


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Нет активного действия для отмены.")
        return
    await state.clear()
    await message.answer("❌ Действие отменено.")


@router.message(Command("tasks"))
async def cmd_tasks(message: Message) -> None:
    await _show_tasks_page(message, offset=0)


async def _show_tasks_page(message_or_callback, offset: int = 0, edit: bool = False) -> None:
    user_id = message_or_callback.from_user.id
    async with async_session() as db:
        result = await db.execute(
            select(Task)
            .where(and_(Task.user_id == user_id, Task.is_completed == 0))
            .order_by(Task.deadline_dt)
            .offset(offset)
            .limit(TASKS_PER_PAGE + 1)
        )
        tasks = result.scalars().all()

        if not tasks:
            text = "📋 У вас нет активных задач."
            if edit:
                await message_or_callback.message.edit_text(text)
            else:
                await message_or_callback.answer(text)
            return

        has_more = len(tasks) > TASKS_PER_PAGE
        tasks = tasks[:TASKS_PER_PAGE]

        lines = [f"📋 Ваши активные задачи (стр. {offset // TASKS_PER_PAGE + 1}):"]
        for i, t in enumerate(tasks, 1):
            lines.append(f"{offset + i}. «{t.task_text}» → {_format_deadline(t.deadline_dt)}")

        kb = InlineKeyboardBuilder()
        for i, t in enumerate(tasks, 1):
            kb.button(text=str(offset + i), callback_data=TaskSelectCB(task_id=t.task_id, offset=offset))
        if offset > 0:
            kb.button(text="◀️ Назад", callback_data=TaskSelectCB(task_id=0, offset=max(0, offset - TASKS_PER_PAGE)))
        if has_more:
            kb.button(text="Вперёд ▶️", callback_data=TaskSelectCB(task_id=0, offset=offset + TASKS_PER_PAGE))
        kb.adjust(5)

        text = "\n".join(lines)
        if edit:
            await message_or_callback.message.edit_text(text, reply_markup=kb.as_markup())
        else:
            await message_or_callback.answer(text, reply_markup=kb.as_markup())


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    user_id = message.from_user.id
    now = datetime.now()
    start = datetime.combine(now.date(), time.min)
    end = datetime.combine(now.date(), time.max)

    async with async_session() as db:
        result = await db.execute(
            select(Task)
            .where(
                and_(
                    Task.user_id == user_id,
                    Task.is_completed == 0,
                    Task.deadline_dt >= start,
                    Task.deadline_dt <= end,
                )
            )
            .order_by(Task.deadline_dt)
        )
        tasks = result.scalars().all()

        if not tasks:
            await message.answer("📅 На сегодня задач нет. Отдыхайте!")
            return

        lines = ["📅 Задачи на сегодня:"]
        for i, t in enumerate(tasks, 1):
            dl = ""
            if t.deadline_dt and t.deadline_dt.time() != time(0, 0):
                dl = f" — {t.deadline_dt.strftime('%H:%M')}"
            lines.append(f"{i}. «{t.task_text}»{dl}")

        await message.answer("\n".join(lines))


@router.callback_query(TaskSelectCB.filter(F.task_id > 0))
async def on_task_selected(callback: CallbackQuery, callback_data: TaskSelectCB):
    task_id = callback_data.task_id
    offset = callback_data.offset
    async with async_session() as db:
        result = await db.execute(select(Task).where(Task.task_id == task_id))
        task = result.scalar_one_or_none()

        if not task:
            await callback.answer("❌ Задача не найдена.", show_alert=True)
            return

        dl = _format_deadline(task.deadline_dt)
        text = f"📝 Задача: «{task.task_text}»\n⏰ Дедлайн: {dl}\n\nЧто сделать?"

        kb = InlineKeyboardBuilder()
        kb.button(
            text="✏️ Изменить дату/время",
            callback_data=TaskActionCB(task_id=task_id, action="edit", offset=offset)
        )
        kb.button(
            text="✅ Выполнено",
            callback_data=TaskActionCB(task_id=task_id, action="done", offset=offset)
        )
        kb.button(
            text="🔙 Назад к списку",
            callback_data=TaskActionCB(task_id=task_id, action="back", offset=offset)
        )
        kb.adjust(1)

        await callback.message.edit_text(text, reply_markup=kb.as_markup())
        await callback.answer()


@router.callback_query(TaskSelectCB.filter(F.task_id == 0))
async def on_pagination(callback: CallbackQuery, callback_data: TaskSelectCB):
    await _show_tasks_page(callback, offset=callback_data.offset, edit=True)
    await callback.answer()


@router.callback_query(TaskActionCB.filter(F.action == "done"))
async def mark_done(callback: CallbackQuery, callback_data: TaskActionCB):
    task_id = callback_data.task_id
    async with async_session() as db:
        await db.execute(
            update(Task).where(Task.task_id == task_id).values(is_completed=1)
        )
        await db.execute(
            delete(Reminder).where(
                and_(Reminder.task_id == task_id, Reminder.is_sent == 0)
            )
        )
        await db.commit()

    await callback.message.edit_text("✅ Задача выполнена!")
    await callback.answer()


@router.callback_query(TaskActionCB.filter(F.action == "back"))
async def go_back(callback: CallbackQuery, callback_data: TaskActionCB):
    await _show_tasks_page(callback, offset=callback_data.offset, edit=True)
    await callback.answer()


@router.callback_query(TaskActionCB.filter(F.action == "edit"))
async def start_edit(callback: CallbackQuery, callback_data: TaskActionCB, state: FSMContext):
    await state.set_state(EditTaskSG.waiting_datetime)
    await state.update_data(task_id=callback_data.task_id)
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отменить", callback_data=TaskActionCB(task_id=callback_data.task_id, action="back", offset=callback_data.offset))
    await callback.message.edit_text(
        "✏️ Введите новую дату и время.\n\n"
        "Примеры:\n"
        "• 05.08.2026 14:00\n"
        "• завтра в 15:00\n"
        "• через 2 часа\n"
        "• сегодня в 18:30",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@router.message(EditTaskSG.waiting_datetime)
async def process_new_datetime(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data["task_id"]

    new_dt = parse_deadline(message.text)
    if not new_dt:
        await message.answer(
            "❌ Не удалось распознать дату.\n"
            "Попробуйте: '05.08.2026 14:00' или 'завтра в 15:00'"
        )
        return

    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Подтвердить",
        callback_data=TaskConfirmCB(
            task_id=task_id,
            new_dt_ts=int(new_dt.timestamp()),
            confirm=1
        )
    )
    kb.button(
        text="❌ Отменить",
        callback_data=TaskConfirmCB(
            task_id=task_id,
            new_dt_ts=0,
            confirm=0
        )
    )

    await message.answer(
        f"Вы ввели: {message.text}\n"
        f"Распознано: {new_dt.strftime('%d.%m.%Y %H:%M')}\n\n"
        "Подтвердить?",
        reply_markup=kb.as_markup()
    )
    await state.clear()


@router.callback_query(TaskConfirmCB.filter(F.confirm == 1))
async def confirm_edit(callback: CallbackQuery, callback_data: TaskConfirmCB):
    task_id = callback_data.task_id
    new_dt = datetime.fromtimestamp(callback_data.new_dt_ts)

    async with async_session() as db:
        await update_task_deadline(db, task_id, new_dt)

    await callback.message.edit_text(f"✅ Дедлайн обновлён: {new_dt.strftime('%d.%m.%Y %H:%M')}")
    await callback.answer()


@router.callback_query(TaskConfirmCB.filter(F.confirm == 0))
async def cancel_edit(callback: CallbackQuery, callback_data: TaskConfirmCB):
    await callback.message.edit_text("❌ Изменение отменено.")
    await callback.answer()


@router.callback_query(PostponeCB.filter(F.variant == "menu"))
async def show_postpone_menu(callback: CallbackQuery, callback_data: PostponeCB):
    task_id = callback_data.task_id
    kb = InlineKeyboardBuilder()
    kb.button(text="+15 мин", callback_data=PostponeCB(task_id=task_id, variant="15min"))
    kb.button(text="+1 час", callback_data=PostponeCB(task_id=task_id, variant="1hour"))
    kb.button(text="+3 часа", callback_data=PostponeCB(task_id=task_id, variant="3hours"))
    kb.button(text="Завтра", callback_data=PostponeCB(task_id=task_id, variant="tomorrow"))
    kb.button(
        text="✏️ Ввести вручную",
        callback_data=PostponeCB(task_id=task_id, variant="custom")
    )
    kb.adjust(2, 2, 1)

    await callback.message.edit_text("⏸ На сколько перенести задачу?", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(PostponeCB.filter(F.variant.in_(["15min", "1hour", "3hours", "tomorrow"])))
async def postpone_preset(callback: CallbackQuery, callback_data: PostponeCB):
    deltas = {
        "15min": timedelta(minutes=15),
        "1hour": timedelta(hours=1),
        "3hours": timedelta(hours=3),
        "tomorrow": timedelta(days=1),
    }
    delta = deltas[callback_data.variant]
    task_id = callback_data.task_id

    async with async_session() as db:
        result = await db.execute(select(Task).where(Task.task_id == task_id))
        task = result.scalar_one_or_none()
        if not task or not task.deadline_dt:
            await callback.answer("❌ У задачи нет дедлайна.", show_alert=True)
            return

        new_dt = task.deadline_dt + delta
        await update_task_deadline(db, task_id, new_dt)

    await callback.message.edit_text(f"✅ Задача перенесена на {new_dt.strftime('%d.%m.%Y %H:%M')}")
    await callback.answer()


@router.callback_query(PostponeCB.filter(F.variant == "custom"))
async def postpone_custom_start(callback: CallbackQuery, callback_data: PostponeCB, state: FSMContext):
    await state.set_state(PostponeSG.waiting_custom)
    await state.update_data(task_id=callback_data.task_id)
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отменить", callback_data=TaskActionCB(task_id=callback_data.task_id, action="back", offset=0))
    await callback.message.edit_text("✏️ Введите новую дату и время для задачи:", reply_markup=kb.as_markup())
    await callback.answer()


@router.message(PostponeSG.waiting_custom)
async def postpone_custom_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data["task_id"]

    new_dt = parse_deadline(message.text)
    if not new_dt:
        await message.answer("❌ Не распознано. Попробуйте: 'завтра в 15:00'")
        return

    async with async_session() as db:
        await update_task_deadline(db, task_id, new_dt)

    await message.answer(f"✅ Задача перенесена на {new_dt.strftime('%d.%m.%Y %H:%M')}")
    await state.clear()
