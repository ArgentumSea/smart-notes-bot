#!/bin/bash
set -e

cd /opt/smart_notes_bot

echo "=== Копирование admin.py ==="
cp patch/handlers/admin.py handlers/admin.py

echo "=== Патч models.py ==="
python3 << PYEOF
with open("models.py", "r") as f:
    c = f.read()
if "is_blocked" not in c:
    c = c.replace(
        "    created_at = Column(DateTime, default=datetime.now)\n    notes = relationship",
        "    created_at = Column(DateTime, default=datetime.now)\n    is_blocked = Column(Integer, default=0)\n    notes = relationship"
    )
    with open("models.py", "w") as f:
        f.write(c)
    print("models.py OK")
else
    print("models.py already patched")
PYEOF

echo "=== Патч callbacks.py ==="
python3 << PYEOF
with open("callbacks.py", "r") as f:
    c = f.read()
if "AdminUserCB" not in c:
    c += "\n\nclass AdminUserCB(CallbackData, prefix=\"adm_usr\"):\n    user_id: int\n    action: str\n"
    with open("callbacks.py", "w") as f:
        f.write(c)
    print("callbacks.py OK")
else
    print("callbacks.py already patched")
PYEOF

echo "=== Патч notes.py ==="
python3 << PYEOF
with open("handlers/notes.py", "r") as f:
    c = f.read()

# Импорт ADMIN_USER_ID
if "from config import ADMIN_USER_ID" not in c:
    c = c.replace(
        "from note_processor import process_note, format_response",
        "from config import ADMIN_USER_ID\nfrom note_processor import process_note, format_response"
    )

# Проверка блокировки в handle_text
if "if user and user.is_blocked:" not in c:
    old = '@router.message(F.text & ~F.text.startswith("/"), StateFilter(None))\nasync def handle_text(message: Message) -> None:'
    new = '@router.message(F.text & ~F.text.startswith("/"), StateFilter(None))\nasync def handle_text(message: Message) -> None:\n    async with async_session() as db:\n        result = await db.execute(select(User).where(User.user_id == message.from_user.id))\n        user = result.scalar_one_or_none()\n        if user and user.is_blocked:\n            await message.answer("🚫 Доступ заблокирован.")\n            return'
    c = c.replace(old, new)

old_voice = '@router.message(F.voice, StateFilter(None))\nasync def handle_voice(message: Message, bot: Bot) -> None:'
if old_voice in c:
    new_voice = '@router.message(F.voice, StateFilter(None))\nasync def handle_voice(message: Message, bot: Bot) -> None:\n    async with async_session() as db:\n        result = await db.execute(select(User).where(User.user_id == message.from_user.id))\n        user = result.scalar_one_or_none()\n        if user and user.is_blocked:\n            await message.answer("🚫 Доступ заблокирован.")\n            return'
    c = c.replace(old_voice, new_voice)

old_fwd = '@router.message(F.forward_from | F.forward_sender_name, StateFilter(None))\nasync def handle_forward(message: Message) -> None:'
if old_fwd in c:
    new_fwd = '@router.message(F.forward_from | F.forward_sender_name, StateFilter(None))\nasync def handle_forward(message: Message) -> None:\n    async with async_session() as db:\n        result = await db.execute(select(User).where(User.user_id == message.from_user.id))\n        user = result.scalar_one_or_none()\n        if user and user.is_blocked:\n            await message.answer("🚫 Доступ заблокирован.")\n            return'
    c = c.replace(old_fwd, new_fwd)

# Добавить импорт User и select если нет
if "from models import User" not in c:
    c = c.replace(
        "from database import async_session",
        "from database import async_session\nfrom models import User\nfrom sqlalchemy import select"
    )

# /admin в стартовом меню — НОВЫЙ ПОДХОД через поиск блока
if "if message.from_user.id == ADMIN_USER_ID:" not in c:
    start_marker = '@router.message(Command("start"))\nasync def cmd_start(message: Message) -> None:\n    await message.answer('
    start_idx = c.find(start_marker)
    if start_idx != -1:
        # Найти закрывающую скобку блока await message.answer(...)
        search_start = start_idx + len(start_marker)
        paren_depth = 1
        i = search_start
        while i < len(c) and paren_depth > 0:
            if c[i] == "(": paren_depth += 1
            elif c[i] == ")": paren_depth -= 1
            i += 1
        end_idx = i
        old_block = c[start_idx:end_idx]
        new_block = '@router.message(Command("start"))\nasync def cmd_start(message: Message) -> None:\n    lines = [\n        "👋 Привет! Я бот для умных заметок.\n",\n        "📝 Просто напиши мне — я сохраню и сделаю краткое содержание.",\n        "🎙 Можешь прислать голосовое — распознаю текст и покажу его.",\n        "↩️ Пересылай сообщения из других чатов.\n",\n        "⚙️ Команды:",\n        "/tasks — мои задачи",\n        "/today — план на сегодня",\n        "/cancel — отменить текущее действие",\n    ]\n    if message.from_user.id == ADMIN_USER_ID:\n        lines.append("/admin — управление пользователями")\n    await message.answer("\n".join(lines))'
        c = c.replace(old_block, new_block)
        print("cmd_start patched via block replace")
    else
        print("WARNING: cmd_start start_marker not found")
else
    print("cmd_start already patched")

with open("handlers/notes.py", "w") as f:
    f.write(c)
print("notes.py OK")
PYEOF

echo "=== Патч main.py ==="
python3 << PYEOF
with open("main.py", "r") as f:
    c = f.read()

if "from handlers import notes, tasks, admin" not in c:
    c = c.replace(
        "from handlers import notes, tasks",
        "from handlers import notes, tasks, admin"
    )

if "dp.include_router(admin.router)" not in c:
    c = c.replace(
        "dp.include_router(tasks.router)",
        "dp.include_router(tasks.router)\n    dp.include_router(admin.router)"
    )

if 'BotCommand(command="admin"' not in c:
    c = c.replace(
        'BotCommand(command="cancel", description="Отменить текущее действие"),',
        'BotCommand(command="cancel", description="Отменить текущее действие"),\n        BotCommand(command="admin", description="Управление пользователями (админ)"),'
    )

with open("main.py", "w") as f:
    f.write(c)
print("main.py OK")
PYEOF

echo "=== Проверка .env ==="
if ! grep -q "ADMIN_USER_ID" .env; then
    echo "ADMIN_USER_ID=remove personal ID" >> .env
    echo ".env updated"
else
    echo ".env OK"
fi

echo "=== Миграция БД ==="
python3 << PYEOF
import sqlite3, os
db_path = "smart_notes.db"
if not os.path.exists(db_path):
    print("DB not found, skip migration")
else
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in c.fetchall()]
    if "is_blocked" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0")
        conn.commit()
        print("DB migrated: is_blocked added")
    else
        print("DB already has is_blocked")
    conn.close()
PYEOF

echo "=== Очистка кэша ==="
find /opt/smart_notes_bot -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find /opt/smart_notes_bot -name "*.pyc" -delete 2>/dev/null || true

echo "=== Перезапуск бота ==="
systemctl restart smartnotes

echo "=== Готово. Проверь логи: ==="
echo "journalctl -u smartnotes -f --no-hostname"