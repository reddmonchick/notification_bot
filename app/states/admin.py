from aiogram.fsm.state import State, StatesGroup

class OneTimePost(StatesGroup):
    """Состояния для одноразовой рассылки."""
    waiting_for_text = State()
    waiting_for_photo = State()
    waiting_for_time = State()

class ChatManagement(StatesGroup):
    """Состояния для управления общим списком чатов."""
    waiting_for_chat_id_to_add = State()
    waiting_for_chat_id_to_delete = State()

class ScheduledPost(StatesGroup):
    """Состояния для создания рассылки по графику."""
    waiting_for_job_name = State()
    waiting_for_text = State()
    waiting_for_photo = State()
    waiting_for_chat_ids = State()
    waiting_for_cron_times = State()
    waiting_for_pin_decision = State()