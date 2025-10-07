from aiogram import Router, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message

router = Router()

router.message.filter(F.chat.type == "private")

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    await message.answer(
        "Привет! Я бот для автоматической рассылки постов. 🤖\n\n"
        "Для доступа к панели управления используйте команду /admin (доступно только администраторам)."
    )

#@router.message(StateFilter(None)) # Не сработает, если админ в каком-то состоянии
#async def any_other_message(message: Message):
    #"""Обработчик для любых других сообщений от обычных пользователей."""
    #await message.answer(
     #   "Я не понимаю эту команду. 🤖\n\n"
    #    "Если вы администратор, используйте /admin для доступа к панели."
    #)