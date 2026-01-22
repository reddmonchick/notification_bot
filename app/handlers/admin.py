import datetime
import logging
import re
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, Chat
from aiogram.filters import Command, Filter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from ..db import database as db
from ..states.admin import OneTimePost, ChatManagement, ScheduledPost
from ..keyboards import inline as kb
from ..utils.scheduler import send_broadcast, send_scheduled_post
from ..callbacks.callbacks import ScheduledPostAction, ChatPostsAction

from logging_config import setup_logging
setup_logging() 

def get_chat_display_name(chat: Chat) -> str:
    """Возвращает лучшее имя для отображения: 'Название (@username)' или другое."""
    title = chat.title
    username = chat.username
    if title and username:
        return f"{title} (@{username})"
    if username:
        return f"@{username}"
    return title or str(chat.id)

class AdminFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in settings.admin_ids_list

router = Router()
router.message.filter(AdminFilter(), F.chat.type == "private")
router.callback_query.filter(AdminFilter(), F.message.chat.type == "private")

# admin.py

from aiogram.filters import Command, StateFilter
# ... другие импорты

# 👇 ИСПРАВЛЕННЫЙ ХЕНДЛЕР
@router.message(
    ~Command("start", "admin"), # Ловим все сообщения, которые НЕ являются командами /start или /admin
    ~StateFilter(*ScheduledPost.__all_states__, *OneTimePost.__all_states__, *ChatManagement.__all_states__)
)
async def handle_any_admin_message(message: Message, state: FSMContext):
    await state.clear()
    # Проверяем, есть ли в сообщении текст для логгирования
    log_text = f"'{message.text}'" if message.text else f"a non-text message (type: {message.content_type})"
    
    await message.answer("Добро пожаловать в админ-панель!", reply_markup=kb.admin_menu_keyboard())
    logging.info(f"Admin {message.from_user.id} sent {log_text} and redirected to admin panel")

@router.message(Command("admin"))
async def cmd_admin_panel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Добро пожаловать в админ-панель!", reply_markup=kb.admin_menu_keyboard())

@router.callback_query(F.data == "back_to_main_menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("Добро пожаловать в админ-панель!", reply_markup=kb.admin_menu_keyboard())
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer("Добро пожаловать в админ-панель!", reply_markup=kb.admin_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "one_time_post_menu")
async def one_time_post_menu(callback: CallbackQuery):
    try:
        await callback.message.edit_text("Меню одноразовой рассылки:", reply_markup=kb.one_time_post_keyboard())
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer("Меню одноразовой рассылки:", reply_markup=kb.one_time_post_keyboard())
    await callback.answer()

@router.callback_query(F.data == "edit_post")
async def start_edit_post(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OneTimePost.waiting_for_text)
    await callback.message.edit_text("Пришлите текст для одноразовой рассылки.",
                                    reply_markup=kb.back_to_one_time_menu())
    await callback.answer()

@router.message(OneTimePost.waiting_for_text)
async def process_onetime_text(message: Message, state: FSMContext):
    await state.update_data(text=message.html_text)
    await state.set_state(OneTimePost.waiting_for_photo)
    await message.answer("Текст сохранен. Теперь пришлите картинку или нажмите 'Пропустить'.",
                        reply_markup=kb.skip_photo_keyboard())

@router.message(OneTimePost.waiting_for_photo, F.photo)
async def process_onetime_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    user_data = await state.get_data()
    await db.update_post_content(user_data.get('text'), photo_id)
    await state.clear()
    await message.answer("Пост (текст + фото) успешно обновлен!", reply_markup=kb.one_time_post_keyboard())

@router.callback_query(F.data == "skip_photo", StateFilter(OneTimePost.waiting_for_photo))
async def skip_onetime_photo(callback: CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    await db.update_post_content(text=user_data.get('text'), photo_id=None)
    await state.clear()
    await callback.message.edit_text("Пост (только текст) успешно обновлен!",
                                    reply_markup=kb.one_time_post_keyboard())
    await callback.answer()

@router.callback_query(F.data == "set_time")
async def start_set_time(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OneTimePost.waiting_for_time)
    await callback.message.edit_text("Введите время для рассылки: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>", parse_mode="HTML",
                                    reply_markup=kb.back_to_one_time_menu())
    await callback.answer()

@router.message(OneTimePost.waiting_for_time)
async def process_time(message: Message, state: FSMContext, scheduler: AsyncIOScheduler):
    try:
        scheduled_dt = datetime.datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        if scheduled_dt <= datetime.datetime.now():
            await message.answer("Эта дата уже в прошлом.")
            return
        await db.update_post_schedule(message.text)
        await state.clear()
        if scheduler.get_job('broadcast_job'):
            scheduler.reschedule_job('broadcast_job', trigger='date', run_date=scheduled_dt)
            await message.answer(f"Время изменено на {message.text}!", reply_markup=kb.one_time_post_keyboard())
        else:
            await message.answer(f"Время установлено на {message.text}.", reply_markup=kb.one_time_post_keyboard())
    except ValueError:
        await message.answer("Неверный формат. Введите <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>.", parse_mode="HTML")

@router.callback_query(F.data == "status")
async def show_status(callback: CallbackQuery, bot: Bot):
    post_data = await db.get_post_data()
    if not post_data or not (post_data[0] or post_data[1]):
        await callback.answer("Пост еще не настроен.", show_alert=True)
        return

    text, photo_id, scheduled_time, status = post_data
    status_text = "✅ Запущена" if status == 'running' else "⏹️ Остановлена"
    scheduled_time_str = scheduled_time.strftime("%d.%m.%Y %H:%M") if scheduled_time else 'Не установлено'
    caption = f"<b>Статус одноразовой рассылки:</b> {status_text}\n<b>Время:</b> {scheduled_time_str}\n\n{text or ''}"

    try:
        await callback.message.delete()
        if photo_id:
            await bot.send_photo(callback.from_user.id, photo_id, caption=caption,
                                reply_markup=kb.back_to_one_time_menu(), parse_mode="HTML")
        else:
            await callback.message.answer(caption, reply_markup=kb.back_to_one_time_menu(), parse_mode="HTML")
    except Exception as e:
        await callback.message.answer(f"Ошибка: {e}\n\n{caption}", reply_markup=kb.back_to_one_time_menu(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "start_mailing")
async def start_mailing(callback: CallbackQuery, bot: Bot, scheduler: AsyncIOScheduler):
    post_data = await db.get_post_data()
    if not all([post_data, (post_data[0] or post_data[1]), post_data[2]]):
        await callback.answer("Настройте пост и время.", show_alert=True)
        return
    if scheduler.get_job('broadcast_job'):
        await callback.answer("Рассылка уже запущена.", show_alert=True)
        return
    scheduled_dt = post_data[2]
    if scheduled_dt <= datetime.datetime.now():
        await callback.answer("Время рассылки прошло.", show_alert=True)
        return
    scheduler.add_job(send_broadcast, 'date', run_date=scheduled_dt, args=[bot, callback.from_user.id],
                     id='broadcast_job')
    await db.update_post_status('running')
    await callback.message.edit_text(f"✅ Рассылка запланирована на {scheduled_dt.strftime('%d.%m.%Y %H:%M')}!",
                                    reply_markup=kb.one_time_post_keyboard())
    await callback.answer()

@router.callback_query(F.data == "stop_mailing")
async def stop_mailing(callback: CallbackQuery, scheduler: AsyncIOScheduler):
    if scheduler.get_job('broadcast_job'):
        scheduler.remove_job('broadcast_job')
        await db.update_post_status('stopped')
        await callback.message.edit_text("⏹️ Рассылка остановлена.", reply_markup=kb.one_time_post_keyboard())
        await callback.answer("Остановлена.", show_alert=True)
    else:
        await db.update_post_status('stopped')
        await callback.answer("Рассылка не была запущена.", show_alert=True)


@router.callback_query(F.data == "manage_chats")
async def manage_chats_menu(callback: CallbackQuery):
    await callback.message.edit_text("💬 Управление ОБЩИМ списком чатов для одноразовой рассылки:",
                                    reply_markup=kb.chat_management_keyboard())
    await callback.answer()

@router.callback_query(F.data == "add_chat")
async def request_chat_id_to_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ChatManagement.waiting_for_chat_id_to_add)
    await callback.message.edit_text("Пришлите ID или username чата (@username) для добавления в ОБЩИЙ список:",
                                    reply_markup=kb.back_to_chat_menu())
    await callback.answer()

@router.message(ChatManagement.waiting_for_chat_id_to_add)
async def process_add_chat(message: Message, state: FSMContext, bot: Bot):
    input_text = message.text.strip()
    try:
        if input_text.startswith('@'):
            chat = await bot.get_chat(input_text)
        else:
            chat = await bot.get_chat(int(input_text))
        
        display_name = get_chat_display_name(chat)
        response = await db.add_chat(chat.id)

        if "уже есть" in response:
            await message.answer(f"⚠️ Чат/канал '{display_name}' уже добавлен!")
        else:
            await message.answer(f"✅ Чат/канал '{display_name}' успешно добавлен!")
        
        await state.clear()
        await message.answer("💬 Меню управления чатами:", reply_markup=kb.chat_management_keyboard())
    except (ValueError, TypeError):
        await message.answer("⚠️ Неверный формат ID. Введите числовой ID или @username.")
    except TelegramAPIError as e:
        await message.answer(
            f"⚠️ Ошибка: не могу найти чат {input_text}. Убедитесь, что бот админ и чат существует.\nОшибка: {e}")

@router.callback_query(F.data == "delete_chat")
async def request_chat_id_to_delete(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ChatManagement.waiting_for_chat_id_to_delete)
    await callback.message.edit_text("Пришлите ID или username чата (@username) для удаления из ОБЩЕГО списка:",
                                    reply_markup=kb.back_to_chat_menu())
    await callback.answer()

@router.message(ChatManagement.waiting_for_chat_id_to_delete)
async def process_delete_chat(message: Message, state: FSMContext, bot: Bot):
    input_text = message.text.strip()
    try:
        if input_text.startswith('@'):
            chat = await bot.get_chat(input_text)
            chat_id = chat.id
        else:
            chat_id = int(input_text)
        response = await db.delete_chat(chat_id)
        await message.answer(response)
        await state.clear()
        await message.answer("💬 Меню управления чатами:", reply_markup=kb.chat_management_keyboard())
    except (ValueError, TypeError):
        await message.answer("⚠️ Неверный формат ID. Введите числовой ID или @username.")
    except TelegramAPIError as e:
        await message.answer(f"⚠️ Ошибка: не могу найти чат {input_text}.\nОшибка: {e}")

@router.callback_query(F.data == "list_chats")
async def show_chat_list(callback: CallbackQuery, bot: Bot):
    chat_ids = await db.get_all_chats()
    if not chat_ids:
        await callback.message.edit_text("📋 ОБЩИЙ список чатов пуст.", reply_markup=kb.chat_management_keyboard())
        await callback.answer()
        return

    chat_details = []
    for chat_id in chat_ids:
        try:
            tg_chat = await bot.get_chat(chat_id)
            display_name = get_chat_display_name(tg_chat)
            chat_details.append({'title': display_name, 'chat_id': chat_id})
        except TelegramAPIError:
            chat_details.append({'title': f"НЕИЗВЕСТНЫЙ ЧАТ ({chat_id})", 'chat_id': chat_id})
    
    text = "📋 ОБЩИЙ список чатов:\n\n" + "\n".join(f"• {c['title']} (<code>{c['chat_id']}</code>)" for c in chat_details)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.chat_management_keyboard())
    await callback.answer()


@router.callback_query(F.data == "list_chats_with_posts")
async def list_chats_with_posts(callback: CallbackQuery, bot: Bot):
    posts = await db.get_all_scheduled_posts()
    all_chat_ids = set()
    for post in posts:
        if post.get('chat_ids'):
            all_chat_ids.update(post['chat_ids'])

    if not all_chat_ids:
        await callback.message.edit_text("📋 Чатов с рассылками по графику нет.", reply_markup=kb.scheduled_posts_menu_keyboard())
        await callback.answer()
        return
    
    chats_for_keyboard = []
    for chat_id in sorted(list(all_chat_ids)):
        try:
            tg_chat = await bot.get_chat(chat_id)
            chats_for_keyboard.append({'chat_id': chat_id, 'title': get_chat_display_name(tg_chat)})
        except TelegramAPIError:
            chats_for_keyboard.append({'chat_id': chat_id, 'title': f"НЕИЗВЕСТНЫЙ ЧАТ ({chat_id})"})

    await callback.message.edit_text("📬 Выберите чат для просмотра рассылок:",
                                    reply_markup=kb.list_chats_with_posts_keyboard(chats_for_keyboard))
    await callback.answer()

@router.callback_query(ChatPostsAction.filter(F.action == "view"))
async def view_chat_posts(callback: CallbackQuery, bot: Bot, callback_data: ChatPostsAction):
    chat_id = callback_data.chat_id
    try:
        tg_chat = await bot.get_chat(chat_id)
        chat_title = get_chat_display_name(tg_chat)
    except TelegramAPIError:
        chat_title = str(chat_id)

    posts = await db.get_posts_by_chat_id(chat_id)
    if not posts:
        await callback.message.edit_text(f"📬 Для чата '<b>{chat_title}</b>' нет рассылок по графику.",
                                        reply_markup=kb.back_to_scheduled_menu(), parse_mode="HTML")
        await callback.answer()
        return
        
    text = f"📬 Рассылки для чата '<b>{chat_title}</b>':"
    await callback.message.edit_text(text, reply_markup=kb.chat_posts_keyboard(posts, chat_id), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "scheduled_posts_menu")
async def scheduled_posts_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("📅 Управление рассылками по графику:",
                                    reply_markup=kb.scheduled_posts_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data == "list_scheduled_posts")
async def list_scheduled_posts(callback: CallbackQuery):
    posts = await db.get_all_scheduled_posts()
    text = "📋 Выберите рассылку для управления:"
    if not posts:
        text = "📋 Рассылок нет."
    await callback.message.edit_text(text, reply_markup=kb.list_scheduled_posts_keyboard(posts))
    await callback.answer()

@router.callback_query(F.data == "create_scheduled_post")
async def create_scheduled_post_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ScheduledPost.waiting_for_job_name)
    await callback.message.edit_text(
        "<b>Шаг 1/5:</b> Придумайте уникальное имя для этой рассылки (латиницей, без пробелов, например, <code>visa_b1</code>).",
        parse_mode="HTML", reply_markup=kb.back_to_scheduled_menu())
    await callback.answer()

@router.message(ScheduledPost.waiting_for_job_name)
async def process_job_name(message: Message, state: FSMContext):
    job_name = message.text.strip()
    if not re.match("^[a-zA-Z0-9_-]+$", job_name):
        await message.answer("Имя может содержать только латинские буквы, цифры, дефис и подчеркивание. Попробуйте еще раз.")
        return
    if await db.get_scheduled_post_by_name(job_name):
        await message.answer("Рассылка с таким именем уже существует. Придумайте другое.")
        return
    await state.update_data(job_name=job_name)
    await state.set_state(ScheduledPost.waiting_for_text)
    await message.answer("<b>Шаг 2/5:</b> Отлично. Теперь пришлите текст поста.")

@router.message(ScheduledPost.waiting_for_text)
async def process_scheduled_text(message: Message, state: FSMContext):
    await state.update_data(text=message.html_text)
    await state.set_state(ScheduledPost.waiting_for_photo)
    await message.answer("<b>Шаг 3/5:</b> Текст сохранен. Пришлите картинку или нажмите 'Пропустить'.",
                        reply_markup=kb.skip_photo_keyboard())

@router.message(ScheduledPost.waiting_for_photo, F.photo)
async def process_scheduled_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(ScheduledPost.waiting_for_chat_ids)
    await message.answer(
        "<b>Шаг 4/5:</b> Картинка сохранена. Теперь пришлите ID или username чатов (@username), через запятую.\n\nНапример: <code>@mychannel, -100123456, @mygroup</code>", parse_mode="HTML")

@router.callback_query(F.data == "skip_photo", StateFilter(ScheduledPost.waiting_for_photo))
async def skip_scheduled_photo(callback: CallbackQuery, state: FSMContext):
    await state.update_data(photo_id=None)
    await state.set_state(ScheduledPost.waiting_for_chat_ids)
    await callback.message.edit_text(
        "<b>Шаг 4/5:</b> Фото пропущено. Теперь пришлите ID или username чатов (@username), через запятую.\n\nНапример: <code>@mychannel, -100123456</code>", parse_mode="HTML")
    await callback.answer()

@router.message(ScheduledPost.waiting_for_chat_ids)
async def process_scheduled_chat_ids(message: Message, state: FSMContext, bot: Bot):
    try:
        chat_inputs = [chat_id.strip() for chat_id in message.text.split(',')]
        chat_ids = []
        for input_text in chat_inputs:
            if input_text.startswith('@'):
                chat = await bot.get_chat(input_text)
                chat_ids.append(chat.id)
            else:
                chat_id = int(input_text)
                await bot.get_chat(chat_id)
                chat_ids.append(chat_id)
        await state.update_data(chat_ids=chat_ids)
        await state.set_state(ScheduledPost.waiting_for_cron_times)
        await message.answer(
            "<b>Шаг 5/5:</b> Чаты сохранены. Теперь укажите время отправки (в 24-часовом формате, через запятую).\n\nНапример, чтобы отправлять в 10:00 и 19:00, напишите: <code>10:00, 19:00</code>", parse_mode="HTML")
    except (ValueError, TypeError):
        await message.answer(
            "Ошибка. Убедитесь, что вы ввели числовые ID или @username, разделённые запятыми. Например: <code>@mychannel, -100123456</code>", parse_mode="HTML")
    except TelegramAPIError as e:
        await message.answer(
            f"Ошибка: не могу найти один из чатов. Убедитесь, что бот админ и чаты существуют.\nОшибка: {e}")

@router.message(ScheduledPost.waiting_for_cron_times)
async def process_scheduled_cron_times(message: Message, state: FSMContext):
    times = [t.strip() for t in message.text.split(',')]
    hours, minutes = set(), set()
    try:
        for t in times:
            h, m = map(int, t.split(':'))
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
            hours.add(str(h))
            minutes.add(str(m))

        await state.update_data(
            cron_hour=','.join(sorted(list(hours))),
            cron_minute=','.join(sorted(list(minutes)))
        )
        
        await state.set_state(ScheduledPost.waiting_for_pin_decision)
        await message.answer(
            "<b>Шаг 5/5:</b> Время сохранено. Закрепить сообщение в чатах при отправке?",
            parse_mode="HTML",
            reply_markup=kb.pin_message_keyboard()
        )
    except ValueError:
        await message.answer(
            "Ошибка формата времени. Введите время как <code>ЧЧ:ММ</code>. Если времен несколько, разделите их запятой. Например: <code>08:30, 21:00</code>",
            parse_mode="HTML",
            reply_markup=kb.back_to_scheduled_menu()
        )
        await state.clear()

@router.callback_query(F.data.in_({"pin_yes", "pin_no", "pin_silent"}), StateFilter(ScheduledPost.waiting_for_pin_decision))
async def process_pin_decision(callback: CallbackQuery, state: FSMContext, scheduler: AsyncIOScheduler, bot: Bot):
    await callback.message.delete()
    
    data = await state.get_data()
    logging.info(f"Pin decision - callback.data: {callback.data}, state data: {data}")
    
    required_keys = ['job_name', 'text', 'photo_id', 'chat_ids', 'cron_hour', 'cron_minute']
    missing_keys = [key for key in required_keys if key not in data]
    if missing_keys:
        await callback.message.answer(
            f"Ошибка: не завершён процесс создания рассылки. Отсутствуют данные: {', '.join(missing_keys)}. Пожалуйста, начните создание рассылки заново.",
            reply_markup=kb.scheduled_posts_menu_keyboard()
        )
        await state.clear()
        await callback.answer("Процесс создания прерван.", show_alert=True)
        return
    
    pin_message = callback.data == "pin_yes"
    pin_silent = callback.data == "pin_silent"
    data['pin_message'] = pin_message
    data['pin_silent'] = pin_silent
    logging.info(f"Saving to DB: job_name={data['job_name']}, pin_message={pin_message}, pin_silent={pin_silent}")
    
    response = await db.add_scheduled_post(data)

    scheduler.add_job(
        send_scheduled_post,
        'cron',
        hour=data['cron_hour'],
        minute=data['cron_minute'],
        args=[bot, data['job_name'], callback.from_user.id],
        id=data['job_name']
    )

    await callback.message.answer(response, reply_markup=kb.scheduled_posts_menu_keyboard())
    await state.clear()
    await callback.answer()

@router.callback_query(ScheduledPostAction.filter(F.action == "view"))
async def view_scheduled_post(callback: CallbackQuery, bot: Bot, callback_data: ScheduledPostAction):
    job_name = callback_data.job_name
    chat_id = callback_data.chat_id

    post = await db.get_scheduled_post_by_name(job_name)
    if not post:
        await callback.answer("Рассылка не найдена.", show_alert=True)
        return

    status_icon = "✅ Активна" if post['status'] == 'active' else "⏸️ На паузе"
    pin_status = "🔇 Да, без уведомления" if post.get('pin_silent') else ("✅ Да" if post.get('pin_message') else "❌ Нет")
    
    times_list = []
    for h in post['cron_hour'].split(','):
        for m in post['cron_minute'].split(','):
            times_list.append(f"{int(h):02d}:{int(m):02d}")
    times = ", ".join(sorted(times_list))

    chats = []
    if post.get('chat_ids'):
        for cid in post['chat_ids']:
            try:
                chat = await bot.get_chat(cid)
                chats.append(get_chat_display_name(chat))
            except TelegramAPIError:
                chats.append(str(cid))
    chats_str = ", ".join(chats)

    text = (
        f"<b>Рассылка:</b> <code>{job_name}</code>\n"
        f"<b>Статус:</b> {status_icon}\n"
        f"<b>Закрепить:</b> {pin_status}\n"
        f"<b>Время (UTC):</b> {times}\n"
        f"<b>Чаты:</b> {chats_str}\n\n"
        f"{post.get('text', '')}"
    )

    try:
        await callback.message.delete()
        reply_markup = kb.scheduled_post_details_keyboard(job_name, post['status'], chat_id)
        if post.get('photo_id'):
            await bot.send_photo(callback.from_user.id, post['photo_id'], caption=text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        await callback.message.answer(f"Ошибка: {e}\n\n{text}", reply_markup=reply_markup, parse_mode="HTML")
    await callback.answer()

@router.callback_query(ScheduledPostAction.filter(F.action == "toggle"))
async def toggle_scheduled_post(callback: CallbackQuery, scheduler: AsyncIOScheduler, callback_data: ScheduledPostAction, bot: Bot):
    job_name = callback_data.job_name
    chat_id = callback_data.chat_id

    post = await db.get_scheduled_post_by_name(job_name)
    if not post:
        await callback.answer("Рассылка не найдена.", show_alert=True)
        return

    job = scheduler.get_job(job_name)
    new_status = 'paused' if post['status'] == 'active' else 'active'

    if new_status == 'paused' and job:
        job.pause()
        msg = "⏸️ Рассылка поставлена на паузу."
    elif new_status == 'active' and job:
        job.resume()
        msg = "▶️ Рассылка возобновлена."
    else:
        msg = "▶️ Рассылка активирована. Она запустится в следующее запланированное время."

    await db.update_scheduled_post_status(job_name, new_status)
    await callback.answer(msg, show_alert=True)

    await callback.message.delete()
    reply_markup = kb.scheduled_post_details_keyboard(job_name, new_status, chat_id)
    
    status_icon = "✅ Активна" if new_status == 'active' else "⏸️ На паузе"
    pin_status = "🔇 Да, без уведомления" if post.get('pin_silent') else ("✅ Да" if post.get('pin_message') else "❌ Нет")
    times_list = [f"{int(h):02d}:{int(m):02d}" for h in post['cron_hour'].split(',') for m in post['cron_minute'].split(',')]
    times = ", ".join(sorted(times_list))
    chats = [get_chat_display_name(await bot.get_chat(cid)) for cid in post.get('chat_ids', [])]
    chats_str = ", ".join(chats)
    
    text = (
        f"<b>Рассылка:</b> <code>{job_name}</code>\n"
        f"<b>Статус:</b> {status_icon}\n"
        f"<b>Закрепить:</b> {pin_status}\n"
        f"<b>Время (UTC):</b> {times}\n"
        f"<b>Чаты:</b> {chats_str}\n\n"
        f"{post.get('text', '')}"
    )
    
    if post.get('photo_id'):
        await bot.send_photo(callback.from_user.id, post['photo_id'], caption=text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")

@router.callback_query(ScheduledPostAction.filter(F.action == "delete"))
async def delete_scheduled_post_confirm(callback: CallbackQuery, callback_data: ScheduledPostAction):
    job_name = callback_data.job_name
    chat_id = callback_data.chat_id
    
    text = f"Вы уверены, что хотите удалить рассылку <code>{job_name}</code>? Это действие необратимо."
    
    reply_markup = kb.confirm_delete_keyboard(job_name, chat_id)
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)
    await callback.answer("Подтвердите удаление.", show_alert=True)

@router.callback_query(ScheduledPostAction.filter(F.action == "confirm_delete"))
async def delete_scheduled_post_execute(callback: CallbackQuery, bot: Bot, scheduler: AsyncIOScheduler, callback_data: ScheduledPostAction):
    job_name = callback_data.job_name
    chat_id = callback_data.chat_id

    if scheduler.get_job(job_name):
        scheduler.remove_job(job_name)
    await db.delete_scheduled_post(job_name)
    await callback.answer("Рассылка удалена.", show_alert=True)

    await callback.message.delete()
    posts = await db.get_all_scheduled_posts()
    text = "📋 Выберите рассылку для управления:"
    if not posts:
        text = "📋 Рассылок нет."
    await callback.message.answer(text, reply_markup=kb.list_scheduled_posts_keyboard(posts))