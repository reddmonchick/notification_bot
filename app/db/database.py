import asyncpg
from typing import Optional, Tuple, List, Dict, Any
from config import settings
from datetime import datetime
import logging

from app.logging_config import setup_logging
setup_logging() 

pool = None

async def get_pool():
    global pool
    if pool is None:
        try:
            pool = await asyncpg.create_pool(dsn=settings.database_url)
        except Exception as e:
            print(f"Не удалось подключиться к базе данных: {e}")
            raise
    return pool

async def initialize_db():
    """Инициализирует все таблицы в базе данных."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS post (
                id INT PRIMARY KEY,
                text TEXT,
                photo_id TEXT,
                scheduled_time TIMESTAMP,
                status VARCHAR(10) DEFAULT 'stopped'
            )
        """)
        if not await conn.fetchval("SELECT id FROM post WHERE id = 1"):
            await conn.execute("INSERT INTO post (id) VALUES (1)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id BIGINT PRIMARY KEY
            )
        """)
        
        # 👇 ПОЛНЫЙ И КОРРЕКТНЫЙ ЗАПРОС
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id SERIAL PRIMARY KEY,
                job_name TEXT UNIQUE NOT NULL,
                text TEXT,
                photo_id TEXT,
                chat_ids BIGINT[],
                cron_hour TEXT,
                cron_minute TEXT,
                status VARCHAR(10) DEFAULT 'active',
                pin_message BOOLEAN DEFAULT FALSE,
                pin_silent BOOLEAN DEFAULT FALSE
            )
        """)
    print("База данных успешно инициализирована.")

async def add_chat(chat_id: int) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute("INSERT INTO chats (chat_id) VALUES ($1)", chat_id)
            return f"✅ Чат `{chat_id}` успешно добавлен в ОБЩИЙ список."
        except asyncpg.UniqueViolationError:
            return f"⚠️ Чат `{chat_id}` уже есть в ОБЩЕМ списке."

async def delete_chat(chat_id: int) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM chats WHERE chat_id = $1", chat_id)
        return f"🗑️ Чат `{chat_id}` удален из ОБЩЕГО списка." if result == 'DELETE 1' else f"⚠️ Чат `{chat_id}` не найден."

async def get_all_chats() -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        chats_rows = await conn.fetch("SELECT chat_id FROM chats")
        return [row['chat_id'] for row in chats_rows]

async def get_posts_by_chat_id(chat_id: int) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM scheduled_posts WHERE $1 = ANY(chat_ids)", chat_id)
        return [dict(row) for row in rows]

async def migrate_chat_id(old_chat_id: int, new_chat_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if await conn.fetchval("SELECT chat_id FROM chats WHERE chat_id = $1", new_chat_id):
            await conn.execute("DELETE FROM chats WHERE chat_id = $1", old_chat_id)
        else:
            await conn.execute("UPDATE chats SET chat_id = $1 WHERE chat_id = $2", new_chat_id, old_chat_id)
        await conn.execute("UPDATE scheduled_posts SET chat_ids = array_replace(chat_ids, $1, $2)", old_chat_id, new_chat_id)

async def update_post_content(text: str, photo_id: Optional[str]):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE post SET text = $1, photo_id = $2 WHERE id = 1", text, photo_id)

async def update_post_schedule(scheduled_time_str: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        dt_obj = datetime.strptime(scheduled_time_str, "%d.%m.%Y %H:%M")
        await conn.execute("UPDATE post SET scheduled_time = $1 WHERE id = 1", dt_obj)

async def update_post_status(status: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE post SET status = $1 WHERE id = 1", status)

async def get_post_data() -> Optional[Tuple]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT text, photo_id, scheduled_time, status FROM post WHERE id = 1")
        return tuple(row.values()) if row else None

async def add_scheduled_post(data: Dict[str, Any]) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            logging.info(f"Inserting into DB: job_name={data['job_name']}, pin_message={data.get('pin_message', False)}, pin_silent={data.get('pin_silent', False)}")
            await conn.execute("""
                INSERT INTO scheduled_posts (job_name, text, photo_id, chat_ids, cron_hour, cron_minute, pin_message, pin_silent, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'active')
            """,
            data['job_name'],
            data.get('text'),
            data.get('photo_id'),
            data['chat_ids'],
            data['cron_hour'],
            data['cron_minute'],
            data.get('pin_message', False),
            data.get('pin_silent', False)
            )
            return "✅ Новая рассылка по графику успешно создана и активирована."
        except asyncpg.UniqueViolationError:
            return f"⚠️ Рассылка с именем `{data['job_name']}` уже существует. Выберите другое имя."

async def get_all_scheduled_posts() -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM scheduled_posts ORDER BY job_name")
        return [dict(row) for row in rows]

async def get_scheduled_post_by_name(job_name: str) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM scheduled_posts WHERE job_name = $1", job_name)
        return dict(row) if row else None

async def delete_scheduled_post(job_name: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM scheduled_posts WHERE job_name = $1", job_name)

async def update_scheduled_post_status(job_name: str, status: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE scheduled_posts SET status = $1 WHERE job_name = $2", status, job_name)