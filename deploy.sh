#!/bin/bash
set -e

REPO_URL="https://github.com/ArgentumSea/smart-notes-bot.git"
INSTALL_DIR="/opt/smart_notes_bot"
SERVICE_NAME="smartnotes"
VOSK_URL="https://alphacephei.com/vosk/models/vosk-model-ru-0.42.zip"

echo "=== Smart Notes Bot — Deploy ==="

# 1. Зависимости
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip ffmpeg git wget unzip curl

# 2. Пользователь
if ! id -u botuser &>/dev/null; then
    useradd -r -s /bin/false botuser
fi

# 3. Клонирование
rm -rf "$INSTALL_DIR"
git clone "$REPO_URL" "$INSTALL_DIR"
chown -R botuser:botuser "$INSTALL_DIR"

# 4. Окружение
su - botuser -s /bin/bash -c "python3 -m venv $INSTALL_DIR/venv"
su - botuser -s /bin/bash -c "$INSTALL_DIR/venv/bin/pip install --upgrade pip -q"
su - botuser -s /bin/bash -c "$INSTALL_DIR/venv/bin/pip install -r $INSTALL_DIR/requirements.txt -q"

# 5. .env (nano)
cat > "$INSTALL_DIR/.env" << 'EOF'
BOT_TOKEN=
GEMINI_API_KEY=
DATABASE_URL=sqlite+aiosqlite:///opt/smart_notes_bot/smart_notes.db
VOSK_MODEL_PATH=/opt/vosk-model-ru
TIMEZONE=Europe/Moscow
LOG_PATH=/var/log/smartnotes/bot.log
EOF

chown botuser:botuser "$INSTALL_DIR/.env"
nano "$INSTALL_DIR/.env"

# Валидация
if ! grep -q "^BOT_TOKEN=[^[:space:]]" "$INSTALL_DIR/.env"; then
    echo "❌ BOT_TOKEN не заполнен"
    exit 1
fi
if ! grep -q "^GEMINI_API_KEY=[^[:space:]]" "$INSTALL_DIR/.env"; then
    echo "❌ GEMINI_API_KEY не заполнен"
    exit 1
fi
chmod 600 "$INSTALL_DIR/.env"

# 6. Vosk
mkdir -p /opt/vosk-model-ru
if [ ! -f "/opt/vosk-model-ru/graph/HCLr.fst" ]; then
    wget -q --show-progress "$VOSK_URL" -O /tmp/vosk.zip
    unzip -q /tmp/vosk.zip -d /tmp/vosk-tmp
    mv /tmp/vosk-tmp/vosk-model-ru-0.42/* /opt/vosk-model-ru/
    rm -rf /tmp/vosk-tmp /tmp/vosk.zip
fi
chown -R botuser:botuser /opt/vosk-model-ru

# 7. Логи
mkdir -p /var/log/smartnotes
chown botuser:botuser /var/log/smartnotes

# 8. Таймзона
timedatectl set-timezone Europe/Moscow || true

# 9. Systemd
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=Smart Notes Telegram Bot
After=network.target

[Service]
Type=simple
User=botuser
Group=botuser
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

# 10. Применить патчи админки (миграция БД, подключение хендлеров)
bash "$INSTALL_DIR/patch/apply.sh"

echo ""
echo "=== Готово ==="
echo "journalctl -u $SERVICE_NAME -f"