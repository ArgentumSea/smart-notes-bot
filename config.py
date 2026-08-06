"""Конфигурация бота. Загружает переменные из .env."""

import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY не найден в .env")

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///smart_notes.db")
VOSK_MODEL_PATH: str = os.getenv("VOSK_MODEL_PATH", "/opt/vosk-model-ru")
TIMEZONE: str = os.getenv("TIMEZONE", "Europe/Moscow")
TZ = ZoneInfo(TIMEZONE)
LOG_PATH: str = os.getenv("LOG_PATH", "/var/log/smartnotes/bot.log")
ADMIN_USER_ID: int = int(os.getenv("ADMIN_USER_ID", "0"))

# Пул моделей Gemini для rotation (приоритет сверху вниз)
GEMINI_MODELS: list[str] = [
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]
