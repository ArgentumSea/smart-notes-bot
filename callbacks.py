"""Все CallbackData фабрики в одном месте.
Избегаем двоеточий в данных — используем Unix timestamp (int) для дат."""

from aiogram.filters.callback_data import CallbackData


class TaskSelectCB(CallbackData, prefix="tsk_sel"):
    task_id: int
    offset: int = 0


class TaskActionCB(CallbackData, prefix="tsk_act"):
    task_id: int
    action: str
    offset: int = 0


class TaskConfirmCB(CallbackData, prefix="tsk_cnf"):
    task_id: int
    new_dt_ts: int
    confirm: int


class PostponeCB(CallbackData, prefix="tsk_pst"):
    task_id: int
    variant: str

class AdminUserCB(CallbackData, prefix="adm_usr"):
    user_id: int
    action: str  # menu, block, unblock, delete, back


class AdminUserCB(CallbackData, prefix="adm_usr"):
    user_id: int
    action: str
