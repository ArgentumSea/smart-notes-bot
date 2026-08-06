"""SQLAlchemy-модели. Все datetime — naive, в локальной таймзоне сервера (MSK)."""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    ForeignKey, CheckConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.now)
    is_blocked = Column(Integer, default=0)

    notes = relationship("Note", back_populates="user")
    tasks = relationship("Task", back_populates="user")


class Note(Base):
    __tablename__ = "notes"

    note_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    content = Column(Text, nullable=False)
    source_type = Column(
        String,
        CheckConstraint("source_type IN ('text', 'voice', 'forward')"),
    )
    summary = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="notes")
    tasks = relationship("Task", back_populates="note")


class Task(Base):
    __tablename__ = "tasks"

    task_id = Column(Integer, primary_key=True, autoincrement=True)
    note_id = Column(Integer, ForeignKey("notes.note_id"))
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    task_text = Column(Text, nullable=False)
    deadline_dt = Column(DateTime)
    is_completed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

    note = relationship("Note", back_populates="tasks")
    user = relationship("User", back_populates="tasks")
    reminders = relationship(
        "Reminder",
        back_populates="task",
        cascade="all, delete-orphan",
    )


class Reminder(Base):
    __tablename__ = "reminders"

    reminder_id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.task_id"), nullable=False)
    reminder_type = Column(
        String,
        CheckConstraint(
            "reminder_type IN "
            "('morning_digest', 'one_hour_before', 'exact_time', 'early_task')"
        ),
    )
    scheduled_time = Column(DateTime, nullable=False)
    is_sent = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

    task = relationship("Task", back_populates="reminders")
