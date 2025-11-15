# database.py
import aiosqlite
import time

DB_NAME = "anon_go.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                gender TEXT,
                mood TEXT,
                last_mood_ts INTEGER DEFAULT 0,
                gender_pref TEXT DEFAULT 'any'
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS active_chats (
                user_id INTEGER PRIMARY KEY,
                partner_id INTEGER
            );
        """)
        await db.commit()

async def add_user(user_id, username=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, last_mood_ts, gender_pref) VALUES (?, ?, ?, ?)",
            (user_id, username, 0, 'any')
        )
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute(
            "SELECT user_id, username, gender, mood, last_mood_ts, gender_pref FROM users WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "username": row[1],
            "gender": row[2],
            "mood": row[3],
            "last_mood_ts": row[4] or 0,
            "gender_pref": row[5] or 'any'
        }

async def set_gender(user_id, gender):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET gender=? WHERE user_id=?", (gender, user_id))
        await db.commit()

async def set_mood(user_id, mood):
    ts = int(time.time())
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET mood=?, last_mood_ts=? WHERE user_id=?", (mood, ts, user_id))
        await db.commit()

async def set_gender_pref(user_id, pref):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET gender_pref=? WHERE user_id=?", (pref, user_id))
        await db.commit()

async def get_last_mood_ts(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("SELECT last_mood_ts FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
