from aiogram.filters.callback_data import CallbackData

class ScheduledPostAction(CallbackData, prefix="sched"):
    action: str  # view, toggle, delete, confirm_delete
    job_name: str
    chat_id: int | None = None

class ChatPostsAction(CallbackData, prefix="chat"):
    action: str  # view
    chat_id: int