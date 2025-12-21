import asyncio
import logging
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError
from typing import List, Optional, Tuple

from ..db import database as db

async def _send_and_pin_message(bot: Bot, chat_id: int, text: Optional[str], photo_id: Optional[str], pin_message: bool, pin_silent: bool):
    """
    Отправляет фото и/или текст как отдельные сообщения.
    Если нужно, закрепляет текстовое сообщение (или фото, если текста нет).
    """
    logging.error(f"Отправка в чат {chat_id}: pin_message={pin_message}, pin_silent={pin_silent}")
    message_to_pin_id = None

    if photo_id:
        photo_message = await bot.send_photo(chat_id, photo_id)
        message_to_pin_id = photo_message.message_id
        logging.error(f"Фото отправлено в чат {chat_id}, message_id={message_to_pin_id}")

    if text:
        text_message = await bot.send_message(chat_id, text, parse_mode="HTML", disable_web_page_preview=True)
        message_to_pin_id = text_message.message_id
        logging.error(f"Текст отправлен в чат {chat_id}, message_id={message_to_pin_id}")

    if pin_message or pin_silent:
        try:
            await bot.pin_chat_message(chat_id, message_to_pin_id, disable_notification=pin_silent)
            logging.error(f"Сообщение {message_to_pin_id} успешно закреплено в чате {chat_id} с disable_notification={pin_silent}")
        except TelegramAPIError as e:
            logging.error(f"Ошибка при закреплении сообщения в чате {chat_id}: {e}")

async def _do_sending(bot: Bot, text: Optional[str], photo_id: Optional[str], chat_ids: List[int], pin_message: bool, pin_silent: bool) -> Tuple[int, int]:
    """Основная логика рассылки по списку чатов."""
    successful, failed = 0, 0
    for chat_id in chat_ids:
        try:
            await _send_and_pin_message(bot, chat_id, text, photo_id, pin_message, pin_silent)
            successful += 1
            logging.error(f"Сообщение успешно отправлено в чат {chat_id}.")
        except TelegramBadRequest as e:
            if "group chat was upgraded to a supergroup chat" in e.message and hasattr(e, 'migrate_to_chat_id'):
                new_chat_id = e.migrate_to_chat_id
                logging.error(f"Чат {chat_id} мигрировал в {new_chat_id}. Обновляю БД и повторяю отправку.")
                try:
                    await db.migrate_chat_id(old_chat_id=chat_id, new_chat_id=new_chat_id)
                    await _send_and_pin_message(bot, new_chat_id, text, photo_id, pin_message, pin_silent)
                    successful += 1
                except Exception as migration_e:
                    failed += 1
                    logging.error(f"Ошибка обработки миграции для чата {chat_id}: {migration_e}")
            else:
                failed += 1
                logging.error(f"Ошибка (BadRequest) в чате {chat_id}: {e}")
        except TelegramAPIError as e:
            failed += 1
            logging.error(f"Ошибка (API) в чате {chat_id}: {e}")
        
        await asyncio.sleep(0.5)
    return successful, failed

async def send_report(bot: Bot, admin_id: int, report_title: str, results: Tuple[int, int], pin_message: bool, pin_silent: bool):
    """Отправляет отчет администратору."""
    successful, failed = results
    if pin_silent:
        status_text = "отправлено и закреплено без уведомления"
    elif pin_message:
        status_text = "отправлено и закреплено"
    else:
        status_text = "отправлено"
    text = (
        f"<b>Отчет о рассылке: {report_title}</b>\n\n"
        f"✅ Успешно {status_text}: {successful}\n"
        f"❌ Ошибок: {failed}"
    )
    try:
        await bot.send_message(admin_id, text, parse_mode="HTML")
    except TelegramAPIError as e:
        logging.error(f"Не удалось отправить отчет администратору {admin_id}: {e}")

async def send_broadcast(bot: Bot, admin_id: int):
    """Выполняет одноразовую рассылку."""
    logging.info("Начинаю ОДНОРАЗОВУЮ рассылку...")
    post_data = await db.get_post_data()
    if not (post_data and (post_data[0] or post_data[1])):
        logging.error("Одноразовая рассылка отменена: пост не настроен.")
        await db.update_post_status('stopped')
        return

    text, photo_id, _, _ = post_data
    chat_ids = await db.get_all_chats()
    if not chat_ids:
        logging.error("Одноразовая рассылка отменена: общий список чатов пуст.")
        await db.update_post_status('stopped')
        await send_report(bot, admin_id, '"Одноразовая рассылка"', (0, 0), pin_message=False, pin_silent=False)
        return

    results = await _do_sending(bot, text, photo_id, chat_ids, pin_message=False, pin_silent=False)
    
    await db.update_post_status('stopped')
    logging.error("Одноразовая рассылка завершена.")
    await send_report(bot, admin_id, '"Одноразовая рассылка"', results, pin_message=False, pin_silent=False)

async def send_scheduled_post(bot: Bot, job_name: str, admin_id: int):
    """Выполняет рассылку по графику."""
    logging.error(f"Начинаю рассылку по графику: '{job_name}'")
    post = await db.get_scheduled_post_by_name(job_name)

    if not post:
        logging.error(f"Рассылка '{job_name}' не найдена в БД. Отмена.")
        return
    if post.get('status') != 'active':
        logging.error(f"Рассылка '{job_name}' на паузе. Пропускаю.")
        return

    text = post.get('text')
    photo_id = post.get('photo_id')
    chat_ids = post.get('chat_ids', [])
    pin_message = post.get('pin_message', False)
    pin_silent = post.get('pin_silent', False)

    if not text and not photo_id:
        logging.error(f"Рассылка '{job_name}' пустая. Пропускаю.")
        return

    results = await _do_sending(bot, text, photo_id, chat_ids, pin_message, pin_silent)
    
    logging.error(f"Рассылка по графику '{job_name}' завершена.")
    await send_report(bot, admin_id, f'"{job_name}"', results, pin_message, pin_silent)