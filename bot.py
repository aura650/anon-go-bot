# bot.py
import logging
import time
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ParseMode
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv
import os

from database import init_db, add_user, get_user, set_gender, set_mood, set_gender_pref, get_last_mood_ts

# In-memory match structures
waiting_users = []           # FIFO waiting list
active_chats = {}            # user_id -> partner_id

# Users who triggered search but need to pick gender/mood first
pending_after_gender = set()
pending_after_mood = set()

# Load .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Keyboards ---
def main_menu_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔍 Search", callback_data="menu_search"),
        InlineKeyboardButton("⚙️ Change Gender", callback_data="menu_change_gender"),
    )
    kb.add(
        InlineKeyboardButton("❓ How it works", callback_data="menu_how"),
        InlineKeyboardButton("🧑‍💼 Support", callback_data="menu_support"),
    )
    return kb

def gender_keyboard():
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("Male ♂️", callback_data="gender_male"),
        InlineKeyboardButton("Female ♀️", callback_data="gender_female"),
        InlineKeyboardButton("Other ⚧️", callback_data="gender_other")
    )
    kb.add(InlineKeyboardButton("Set partner preference", callback_data="menu_set_pref"))
    return kb

def mood_keyboard():
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("😊 Happy", callback_data="mood_happy"),
        InlineKeyboardButton("😢 Sad", callback_data="mood_sad"),
        InlineKeyboardButton("😎 Chill", callback_data="mood_chill"),
        InlineKeyboardButton("😉 Flirty", callback_data="mood_flirty"),
        InlineKeyboardButton("😡 Angry", callback_data="mood_angry"),
        InlineKeyboardButton("🫶 Emotional", callback_data="mood_emotional"),
        InlineKeyboardButton("😌 Calm", callback_data="mood_calm"),
        InlineKeyboardButton("😴 Tired", callback_data="mood_tired")
    )
    return kb

def gender_pref_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Any", callback_data="pref_any"),
        InlineKeyboardButton("Male ♂️", callback_data="pref_male"),
        InlineKeyboardButton("Female ♀️", callback_data="pref_female"),
        InlineKeyboardButton("Other ⚧️", callback_data="pref_other"),
    )
    return kb

# --- Utilities ---
TWO_HOURS = 2 * 60 * 60

async def need_mood(user_id):
    row = await get_user(user_id)
    if not row:
        return True
    last = row.get("last_mood_ts", 0) or 0
    now = int(time.time())
    return (now - last) >= TWO_HOURS

def matches_preferences(a_row, b_row):
    if not a_row or not b_row:
        return True
    a_pref = (a_row.get("gender_pref") or "any").lower()
    b_pref = (b_row.get("gender_pref") or "any").lower()
    a_gender = (a_row.get("gender") or "").lower()
    b_gender = (b_row.get("gender") or "").lower()

    def pref_allows(pref, partner_gender):
        if pref == "any":
            return True
        return pref == partner_gender

    return pref_allows(a_pref, b_gender) and pref_allows(b_pref, a_gender)

async def try_match():
    """
    Walk the waiting_users list and pair the first compatible pairs.
    Note: this modifies waiting_users in place.
    """
    idx = 0
    while idx < len(waiting_users):
        a = waiting_users[idx]
        a_row = await get_user(a)
        paired = False
        for j in range(idx+1, len(waiting_users)):
            b = waiting_users[j]
            b_row = await get_user(b)
            if matches_preferences(a_row, b_row):
                # remove and pair (pop larger index first)
                waiting_users.pop(j)
                waiting_users.pop(idx)
                active_chats[a] = b
                active_chats[b] = a

                mood_a = a_row.get("mood") if a_row else None
                mood_b = b_row.get("mood") if b_row else None

                # Partner found (system message -> italic)
                await bot.send_message(a,
                    f"_Partner found ✌️_\n\n"
                    "/next — find a new partner\n"
                    "/stop — stop this chat\n\n"
                    f"_Partner mood:_ {mood_b if mood_b else 'Unknown'}\n\n"
                    "https://t.me/AnonGoOfficial_bot",
                    parse_mode=ParseMode.MARKDOWN
                )
                await bot.send_message(b,
                    f"_Partner found ✌️_\n\n"
                    "/next — find a new partner\n"
                    "/stop — stop this chat\n\n"
                    f"_Partner mood:_ {mood_a if mood_a else 'Unknown'}\n\n"
                    "https://t.me/AnonGoOfficial_bot",
                    parse_mode=ParseMode.MARKDOWN
                )
                paired = True
                break
        if not paired:
            idx += 1

async def start_search_for(user_id):
    if user_id in active_chats:
        await bot.send_message(user_id, "_You are already in a chat._", parse_mode=ParseMode.MARKDOWN)
        return
    if user_id in waiting_users:
        await bot.send_message(user_id, "_You are already in the queue. Searching..._", parse_mode=ParseMode.MARKDOWN)
        return
    waiting_users.append(user_id)
    await bot.send_message(user_id, "_Searching for a partner..._", parse_mode=ParseMode.MARKDOWN)
    await try_match()

# --- Main menu callbacks ---
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("menu_"))
async def menu_callback(cb: CallbackQuery):
    data = cb.data
    uid = cb.from_user.id
    if data == "menu_search":
        await cb.answer()
        await cmd_search_cb(uid)
    elif data == "menu_change_gender":
        await cb.answer()
        await bot.send_message(uid, "_Select your gender:_", reply_markup=gender_keyboard(), parse_mode=ParseMode.MARKDOWN)
    elif data == "menu_how":
        await cb.answer()
        await bot.send_message(uid,
            "_How it works:_ Type /search to find a partner. Choose gender once and mood each search. Use /next to change, /stop to end.",
            parse_mode=ParseMode.MARKDOWN)
    elif data == "menu_support":
        await cb.answer()
        await bot.send_message(uid, "_For support contact:_ https://t.me/AnonGoSupport", parse_mode=ParseMode.MARKDOWN)

# --- /start ---
@dp.message_handler(commands=['start'])
async def cmd_start(msg: types.Message):
    uid = msg.from_user.id
    # add_user may accept username optional
    await add_user(uid, msg.from_user.username)
    await msg.answer(
        "_👋 Welcome to_ *Anon-Go*!\n"
        "_You can chat anonymously with random people._\n\n"
        "_Type /search to find a new partner_",
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

# --- /search logic (used by button and command) ---
async def cmd_search_cb(user_id):
    # Ensure user exists in DB
    await add_user(user_id)
    row = await get_user(user_id)
    gender = row.get("gender") if row else None

    if not gender:
        pending_after_gender.add(user_id)
        await bot.send_message(user_id, "_Set your gender:_", reply_markup=gender_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    if await need_mood(user_id):
        pending_after_mood.add(user_id)
        await bot.send_message(user_id, "_Tell me your present mood:_", reply_markup=mood_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    await start_search_for(user_id)

@dp.message_handler(commands=['search'])
async def cmd_search(msg: types.Message):
    await cmd_search_cb(msg.from_user.id)

# --- /next ---
@dp.message_handler(commands=['next'])
async def cmd_next(msg: types.Message):
    uid = msg.from_user.id
    if uid in active_chats:
        partner = active_chats.pop(uid, None)
        if partner:
            # remove partner mapping
            active_chats.pop(partner, None)
            # notify partner (system message italic)
            await bot.send_message(partner, "_Your partner has stopped the chat._\n_Type /search to find a new partner_\n\nhttps://t.me/AnonGoOfficial_bot", parse_mode=ParseMode.MARKDOWN)
    await bot.send_message(uid, "_Searching for a partner..._", parse_mode=ParseMode.MARKDOWN)
    await start_search_for(uid)

# --- /stop ---
@dp.message_handler(commands=['stop'])
async def cmd_stop(msg: types.Message):
    uid = msg.from_user.id
    if uid in active_chats:
        partner = active_chats.pop(uid, None)
        if partner:
            active_chats.pop(partner, None)
            await bot.send_message(partner, "_Your partner has stopped the chat._\n_Type /search to find a new partner_\n\nhttps://t.me/AnonGoOfficial_bot", parse_mode=ParseMode.MARKDOWN)
        await bot.send_message(uid, "_You stopped the chat._\n_Type /search to find a new partner_\n\nhttps://t.me/AnonGoOfficial_bot", parse_mode=ParseMode.MARKDOWN)
    else:
        await bot.send_message(uid, "_You are not in a chat. Type /search to start._", parse_mode=ParseMode.MARKDOWN)

# --- Gender callbacks ---
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("gender_"))
async def on_gender_choice(callback: CallbackQuery):
    uid = callback.from_user.id
    gender = callback.data.split("_",1)[1]
    await set_gender(uid, gender)
    await callback.answer()
    await callback.message.edit_text(f"👍 *Gender set:* _{gender}_", parse_mode=ParseMode.MARKDOWN)

    if uid in pending_after_gender:
        pending_after_gender.discard(uid)
        # user must choose mood now
        pending_after_mood.add(uid)
        await bot.send_message(uid, "_Tell me your present mood:_", reply_markup=mood_keyboard(), parse_mode=ParseMode.MARKDOWN)

# --- Gender preference callbacks ---
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("pref_"))
async def on_pref_choice(callback: CallbackQuery):
    uid = callback.from_user.id
    pref = callback.data.split("_",1)[1]
    await set_gender_pref(uid, pref)
    await callback.answer()
    await callback.message.edit_text(f"👍 *Preference set:* _{pref}_", parse_mode=ParseMode.MARKDOWN)

# --- Mood callbacks ---
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("mood_"))
async def on_mood_choice(callback: CallbackQuery):
    uid = callback.from_user.id
    mood = callback.data.split("_",1)[1]
    await set_mood(uid, mood)
    await callback.answer()
    await callback.message.edit_text(f"👍 *Your present mood:* _{mood}_", parse_mode=ParseMode.MARKDOWN)

    if uid in pending_after_mood:
        pending_after_mood.discard(uid)
        await start_search_for(uid)

# --- open preference menu ---
@dp.callback_query_handler(lambda c: c.data == "menu_set_pref")
async def open_pref_menu(cb: CallbackQuery):
    await cb.answer()
    await bot.send_message(cb.from_user.id, "_Choose who you want to match with:_", reply_markup=gender_pref_keyboard(), parse_mode=ParseMode.MARKDOWN)

# --- Message forwarding while in chat ---
@dp.message_handler()
async def forward_messages(msg: types.Message):
    uid = msg.from_user.id
    # If user is in an active chat, forward to partner
    if uid in active_chats:
        partner = active_chats.get(uid)
        if not partner:
            await msg.answer("_Error: partner missing._", parse_mode=ParseMode.MARKDOWN)
            return

        try:
            # Forward text (partner receives plain text — not italic)
            if msg.text:
                await bot.send_message(partner, msg.text)
            elif msg.photo:
                # send highest resolution photo (last in list)
                await bot.send_photo(partner, msg.photo[-1].file_id, caption=msg.caption or "")
            elif msg.video:
                await bot.send_video(partner, msg.video.file_id, caption=msg.caption or "")
            elif msg.sticker:
                await bot.send_sticker(partner, msg.sticker.file_id)
            elif msg.animation:
                await bot.send_animation(partner, msg.animation.file_id, caption=msg.caption or "")
            elif msg.document:
                await bot.send_document(partner, msg.document.file_id, caption=msg.caption or "")
            elif msg.voice:
                await bot.send_voice(partner, msg.voice.file_id, caption=msg.caption or "")
            elif msg.audio:
                await bot.send_audio(partner, msg.audio.file_id, caption=msg.caption or "")
            else:
                await bot.send_message(partner, "⚠️ Unsupported message type")
        except Exception as e:
            logger.exception("Failed to forward message from %s to %s: %s", uid, partner, e)
            await msg.answer("_Failed to forward your message. Try /next or /stop._", parse_mode=ParseMode.MARKDOWN)
        return

    # If user is not in a chat, show main menu hint
    await msg.answer("_Type /search to find a partner_", reply_markup=main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN)

# --- Startup ---
async def on_startup(_):
    await init_db()
    print("Database Ready ✔️")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
