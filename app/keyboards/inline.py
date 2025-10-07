from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Dict, Any, Optional
from ..callbacks.callbacks import ScheduledPostAction, ChatPostsAction

def admin_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📨 Одноразовая рассылка", callback_data="one_time_post_menu")],
        [InlineKeyboardButton(text="📅 Рассылки по графику", callback_data="scheduled_posts_menu")],
        [InlineKeyboardButton(text="💬 Управление чатами (для одноразовой)", callback_data="manage_chats")],
        [InlineKeyboardButton(text="📬 Чаты и их рассылки", callback_data="list_chats_with_posts")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def one_time_post_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📝 Изменить пост", callback_data="edit_post")],
        [InlineKeyboardButton(text="⏰ Задать время", callback_data="set_time")],
        [InlineKeyboardButton(text="📊 Статус", callback_data="status")],
        [
            InlineKeyboardButton(text="▶️ Запустить", callback_data="start_mailing"),
            InlineKeyboardButton(text="⏹️ Остановить", callback_data="stop_mailing")
        ],
        [InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_to_main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def back_to_one_time_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="one_time_post_menu")]
    ])

def chat_management_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить чат", callback_data="add_chat")],
        [InlineKeyboardButton(text="🗑️ Удалить чат", callback_data="delete_chat")],
        [InlineKeyboardButton(text="📋 Список чатов", callback_data="list_chats")],
        [InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_to_main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def back_to_chat_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="manage_chats")]
    ])

def scheduled_posts_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="➕ Создать новую", callback_data="create_scheduled_post")],
        [InlineKeyboardButton(text="📋 Список рассылок", callback_data="list_scheduled_posts")],
        [InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_to_main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def back_to_scheduled_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="scheduled_posts_menu")]
    ])

def list_scheduled_posts_keyboard(posts: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons = []
    for post in posts:
        status_icon = "▶️" if post['status'] == 'paused' else "⏸️"
        job_name = post['job_name']
        buttons.append([
            InlineKeyboardButton(
                text=f"📄 {job_name}",
                callback_data=ScheduledPostAction(action="view", job_name=job_name).pack()
            ),
            InlineKeyboardButton(
                text=status_icon,
                callback_data=ScheduledPostAction(action="toggle", job_name=job_name).pack()
            ),
            InlineKeyboardButton(
                text="❌",
                callback_data=ScheduledPostAction(action="delete", job_name=job_name).pack()
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="scheduled_posts_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def scheduled_post_details_keyboard(job_name: str, status: str, chat_id: Optional[int] = None) -> InlineKeyboardMarkup:
    action_text = "▶️ Возобновить" if status == 'paused' else "⏸️ Поставить на паузу"
    back_button_text = "⬅️ К списку рассылок чата" if chat_id else "⬅️ К общему списку"
    back_button_callback = f"chat:view:{chat_id}" if chat_id else "list_scheduled_posts"
    buttons = [
        [
            InlineKeyboardButton(
                text=action_text,
                callback_data=ScheduledPostAction(action="toggle", job_name=job_name, chat_id=chat_id).pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Удалить",
                callback_data=ScheduledPostAction(action="delete", job_name=job_name, chat_id=chat_id).pack()
            )
        ],
        [InlineKeyboardButton(text=back_button_text, callback_data=back_button_callback)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def confirm_delete_keyboard(job_name: str, chat_id: Optional[int] = None) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text="✅ Да, удалить",
                callback_data=ScheduledPostAction(action="confirm_delete", job_name=job_name, chat_id=chat_id).pack()
            ),
            InlineKeyboardButton(
                text="🚫 Отмена",
                callback_data=ScheduledPostAction(action="view", job_name=job_name, chat_id=chat_id).pack()
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def skip_photo_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="➡️ Пропустить", callback_data="skip_photo")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def list_chats_with_posts_keyboard(chats: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons = []
    for chat in chats:
        buttons.append([
            InlineKeyboardButton(
                text=f"💬 {chat['title']}",
                callback_data=ChatPostsAction(action="view", chat_id=chat['chat_id']).pack()
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_to_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def chat_posts_keyboard(posts: List[Dict[str, Any]], chat_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for post in posts:
        status_icon = "▶️" if post['status'] == 'paused' else "⏸️"
        job_name = post['job_name']
        buttons.append([
            InlineKeyboardButton(
                text=f"📄 {job_name}",
                callback_data=ScheduledPostAction(action="view", job_name=job_name, chat_id=chat_id).pack()
            ),
            InlineKeyboardButton(
                text=status_icon,
                callback_data=ScheduledPostAction(action="toggle", job_name=job_name, chat_id=chat_id).pack()
            ),
            InlineKeyboardButton(
                text="❌",
                callback_data=ScheduledPostAction(action="delete", job_name=job_name, chat_id=chat_id).pack()
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в список чатов", callback_data="list_chats_with_posts")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def pin_message_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, закрепить", callback_data="pin_yes")
    kb.button(text="🔇 Закрепить без уведомления", callback_data="pin_silent")
    kb.button(text="❌ Нет, не надо", callback_data="pin_no")
    kb.adjust(1)
    return kb.as_markup()