"""Админ-хендлеры: управление пользователями."""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters.command import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, update, delete, func

from database import async_session
from models import User, Note, Task, Reminder
from callbacks import AdminUserCB
from config import ADMIN_USER_ID

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_USER_ID


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    async with async_session() as db:
        total = await db.execute(select(func.count()).select_from(User))
        total_users = total.scalar()

        result = await db.execute(
            select(User).order_by(User.created_at.desc()).limit(20)
        )
        users = result.scalars().all()

    lines = [f"👤 Всего пользователей: {total_users}\n"]
    for u in users:
        status = "🚫" if u.is_blocked else "✅"
        lines.append(
            f"{status} ID:{u.user_id} | Chat:{u.chat_id} | "
            f"{u.created_at.strftime('%d.%m.%Y')}"
        )

    kb = InlineKeyboardBuilder()
    for u in users:
        icon = "🚫" if u.is_blocked else "✅"
        kb.button(
            text=f"{icon} {u.user_id}",
            callback_data=AdminUserCB(user_id=u.user_id, action="menu")
        )
    kb.adjust(3)

    await message.answer("\n".join(lines), reply_markup=kb.as_markup())


@router.callback_query(AdminUserCB.filter(F.action == "menu"))
async def admin_user_menu(callback: CallbackQuery, callback_data: AdminUserCB):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    user_id = callback_data.user_id
    async with async_session() as db:
        result = await db.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()

    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    status = "заблокирован" if user.is_blocked else "активен"
    text = (
        f"👤 Пользователь {user.user_id}\n"
        f"Chat: {user.chat_id}\n"
        f"Статус: {status}\n"
        f"Зарегистрирован: {user.created_at.strftime('%d.%m.%Y %H:%M')}"
    )

    kb = InlineKeyboardBuilder()
    if user.is_blocked:
        kb.button(
            text="✅ Разблокировать",
            callback_data=AdminUserCB(user_id=user_id, action="unblock")
        )
    else:
        kb.button(
            text="🚫 Заблокировать",
            callback_data=AdminUserCB(user_id=user_id, action="block")
        )
    kb.button(
        text="🗑 Удалить",
        callback_data=AdminUserCB(user_id=user_id, action="delete")
    )
    kb.button(
        text="🔙 Назад",
        callback_data=AdminUserCB(user_id=0, action="back")
    )
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(AdminUserCB.filter(F.action == "block"))
async def admin_block(callback: CallbackQuery, callback_data: AdminUserCB):
    if not is_admin(callback.from_user.id):
        return
    async with async_session() as db:
        await db.execute(
            update(User)
            .where(User.user_id == callback_data.user_id)
            .values(is_blocked=1)
        )
        await db.commit()
    await callback.answer("🚫 Пользователь заблокирован.", show_alert=True)
    await admin_user_menu(callback, callback_data)


@router.callback_query(AdminUserCB.filter(F.action == "unblock"))
async def admin_unblock(callback: CallbackQuery, callback_data: AdminUserCB):
    if not is_admin(callback.from_user.id):
        return
    async with async_session() as db:
        await db.execute(
            update(User)
            .where(User.user_id == callback_data.user_id)
            .values(is_blocked=0)
        )
        await db.commit()
    await callback.answer("✅ Пользователь разблокирован.", show_alert=True)
    await admin_user_menu(callback, callback_data)


@router.callback_query(AdminUserCB.filter(F.action == "delete"))
async def admin_delete(callback: CallbackQuery, callback_data: AdminUserCB):
    if not is_admin(callback.from_user.id):
        return

    user_id = callback_data.user_id
    async with async_session() as db:
        await db.execute(
            delete(Reminder).where(
                Reminder.task_id.in_(
                    select(Task.task_id).where(Task.user_id == user_id)
                )
            )
        )
        await db.execute(delete(Task).where(Task.user_id == user_id))
        await db.execute(delete(Note).where(Note.user_id == user_id))
        await db.execute(delete(User).where(User.user_id == user_id))
        await db.commit()

    await callback.answer(
        "🗑 Пользователь и все его данные удалены.",
        show_alert=True
    )
    await cmd_admin(callback.message)


@router.callback_query(AdminUserCB.filter(F.action == "back"))
async def admin_back(callback: CallbackQuery, callback_data: AdminUserCB):
    if not is_admin(callback.from_user.id):
        return
    await cmd_admin(callback.message)