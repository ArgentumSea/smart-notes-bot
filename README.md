# 🤖 Smart Notes Bot

> Telegram-бот с AI-суммаризацией, извлечением задач, умными напоминаниями и голосовым вводом.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![aiogram](https://img.shields.io/badge/aiogram-3.30-blue)](https://docs.aiogram.dev)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## ✨ Возможности

| Функция | Описание |
|---------|----------|
| 📝 **Умные заметки** | Отправь текст — бот сделает краткое содержание и выделит задачи |
| 🎙 **Голосовой ввод** | Голосовое сообщение → текст → AI-анализ (офлайн через Vosk) |
| ↩️ **Пересылка** | Пересылай сообщения из других чатов — бот сохранит и проанализирует |
| ✅ **Задачи** | Автоматическое извлечение action items с дедлайнами |
| ⏰ **Напоминания** | Утренняя сводка (10:00), за час до дедлайна, в точное время |
| ✏️ **Редактор задач** | Изменяй дедлайны inline, переноси задачи (+15мин / +1ч / +3ч / завтра) |
| 🤖 **AI Rotation** | 4 модели Gemini с автоматическим fallback при исчерпании квоты |
| 🔒 **Безопасность** | Ни один токен или текст заметки не попадает в логи |

---

## 🚀 Быстрый старт

### Автоматический деплой (рекомендуется)

```bash
# На свежем VPS (Ubuntu/Debian)
wget https://raw.githubusercontent.com/YOUR_USERNAME/smart-notes-bot/main/deploy.sh
sudo bash deploy.sh https://github.com/YOUR_USERNAME/smart-notes-bot.git
```

Скрипт сам:
1. Установит все зависимости
2. Склонирует репозиторий
3. Откроет `nano` для ввода токенов
4. Загрузит модель Vosk
5. Настроит и запустит systemd-сервис

### Ручной деплой

```bash
# 1. Клонирование
git clone https://github.com/YOUR_USERNAME/smart-notes-bot.git
cd smart-notes-bot

# 2. Окружение
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. .env
cp .env.example .env
nano .env

# 4. Vosk модель
mkdir -p /opt/vosk-model-ru
wget https://alphacephei.com/vosk/models/vosk-model-ru-0.42.zip
unzip vosk-model-ru-0.42.zip -d /opt/vosk-model-ru

# 5. Запуск
python main.py
```

---

## 🛠 Требования

- **OS:** Ubuntu 20.04+ / Debian 11+
- **Python:** 3.10+
- **RAM:** 2 GB минимум (для Vosk), 4 GB рекомендуется
- **Disk:** 3 GB свободного места (модель Vosk ~1.5 GB)
- **API Keys:**
  - [Telegram Bot Token](https://t.me/BotFather) (бесплатно)
  - [Google Gemini API Key](https://aistudio.google.com/app/apikey) (бесплатный tier)

---

## 📁 Структура проекта

```
smart_notes_bot/
├── .env.example           # Шаблон переменных окружения
├── .gitignore
├── deploy.sh              # Автоматический деплой
├── README.md              # Этот файл
├── requirements.txt       # Зависимости
│
├── config.py              # Конфигурация + timezone
├── database.py            # Инициализация SQLite
├── models.py              # SQLAlchemy модели
├── callbacks.py           # CallbackData фабрики
├── main.py                # Точка входа
│
├── gemini_rotator.py      # AI-модуль (4 модели, fallback, backoff)
├── note_processor.py      # Pipeline: AI → задачи → напоминания
├── voice_recognizer.py    # Vosk: OGG → WAV → текст
│
├── handlers/
│   ├── notes.py           # /start, /help, текст, голос, forward
│   └── tasks.py           # /tasks, /today, FSM-редактор, перенос
│
└── services/
    ├── reminders.py       # Логика создания напоминаний
    └── scheduler.py       # APScheduler (каждую минуту)
```

---

## 🧠 Архитектура

```
Пользователь → Telegram API → aiogram Dispatcher
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
                handle_text    handle_voice     handle_forward
                    │               │               │
                    └───────────────┼───────────────┘
                                    ▼
                          note_processor.process_note()
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              ensure_user()   GeminiRotator    parse_deadline()
                    │               │               │
                    │         (4 модели,        dateparser
                    │          fallback)            │
                    │               │               │
                    └───────────────┼───────────────┘
                                    ▼
                          Сохранение в SQLite
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
                  Note            Task          Reminder
                    │               │               │
                    └───────────────┴───────────────┘
                                    │
                              APScheduler
                                    │
                              send_reminder()
```

---

## 📋 Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и регистрация |
| `/help` | Справка по всем функциям |
| `/tasks` | Список активных задач (с пагинацией) |
| `/today` | Задачи на сегодня |
| `/cancel` | Отменить текущее действие |

**Без команд:** просто отправь текст, голосовое или перешли сообщение.

---

## 🔒 Безопасность

- ✅ API-ключи только в `.env` (chmod 600)
- ✅ Ни один токен не попадает в логи
- ✅ Текст заметок не логируется (только длина при ошибках)
- ✅ Chat ID и PII убраны из логов
- ✅ SQLite и лог-файлы с правами 600
- ✅ Graceful shutdown: `scheduler.shutdown(wait=True)`

---

## 🧪 Технологии

| Компонент | Технология | Версия |
|-----------|------------|--------|
| Telegram Bot | aiogram | 3.30.0 |
| AI | Google Gemini (genai SDK) | 1.0.0 |
| БД | SQLite + SQLAlchemy (async) | 2.0.40 |
| Планировщик | APScheduler | 3.11.3 |
| Распознавание речи | Vosk (офлайн) | 0.3.45 |
| Парсинг дат | dateparser | 1.2.0 |

---

## 📊 AI Rotation Pool

Бот автоматически переключается между 4 моделями Gemini при исчерпании квоты:

1. `gemini-3.5-flash` — основная
2. `gemini-3.6-flash` — резерв
3. `gemini-2.5-flash` — fallback
4. `gemini-2.5-flash-lite` — last resort

При полном исчерпании — exponential backoff (1→2→4→8→60 сек).
