"""Точка входа бота."""

import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from config import BOT_TOKEN, LOG_PATH
from database import init_db
from handlers import notes, tasks, admin, admin
from services.scheduler import setup_scheduler


def setup_logging() -> None:
    log_dir = Path(LOG_PATH).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Приветствие и регистрация"),
        BotCommand(command="help", description="Справка по боту"),
        BotCommand(command="tasks", description="Мои активные задачи"),
        BotCommand(command="today", description="Задачи на сегодня"),
        BotCommand(command="cancel", description="Отменить текущее действие"),
        BotCommand(command="admin", description="Управление пользователями (админ)"),
        BotCommand(command="admin", description="Управление пользователями (админ)"),
    ]
    await bot.set_my_commands(commands)


async def main() -> None:
    setup_logging()
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(notes.router)
    dp.include_router(tasks.router)
    dp.include_router(admin.router)

    await set_commands(bot)

    scheduler = setup_scheduler(bot)
    scheduler.start()

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=True)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
