from aiogram.filters.callback_data import CallbackData

class ScheduledPostAction(CallbackData, prefix="sched"):
    action: str 
    job_name: str
    chat_id: int | None = None

class ChatPostsAction(CallbackData, prefix="chat"):
    action: str 
    chat_id: int