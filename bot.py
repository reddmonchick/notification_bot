import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.client.bot import DefaultBotProperties

from config import settings
from app.handlers import common, admin
from app.db.database import initialize_db

async def main():
    # Настройка логирования для вывода информации в консоль
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    # Инициализация базы данных
    await initialize_db()

    # Инициализация бота и диспетчера
    # В качестве хранилища состояний используем MemoryStorage (данные FSM будут в ОЗУ)
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
    dp = Dispatcher(storage=MemoryStorage())

    # Инициализация планировщика задач
    # Укажите ваш часовой пояс для корректной работы
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow") 
    scheduler.start()

    # Передача планировщика и бота в хендлеры через "мидлварь" диспетчера
    # Это позволяет получать доступ к scheduler и bot в любом хендлере
    dp["scheduler"] = scheduler
    dp["bot"] = bot

    # Подключение роутеров (обработчиков команд)
    dp.include_router(common.router)
    dp.include_router(admin.router)

    print("Бот запущен!")

    # Запуск бота
    # Удаляем вебхук и пропускаем накопившиеся апдейты
    #await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
