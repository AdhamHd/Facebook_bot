import firebase_admin
from firebase_admin import credentials, firestore
from collections import Counter
from zoneinfo import ZoneInfo
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
import asyncio
import queue

# -------- CONFIG --------
BOT_TOKEN = "8566703232:AAEUe1jyhoEdFzYAyFumQ2FdBMRQjCb5FKI"
COLLECTION = "FC DATA"
CAIRO = ZoneInfo("Africa/Cairo")
PASSWORD = "@2468@As"

# =========================
# Firebase 1 (Facebook)
# =========================
cred_facebook_json = os.getenv("FIREBASE_CREDENTIALS")
cred_facebook_dict = json.loads(cred_facebook_json)

cred_facebook = credentials.Certificate(cred_facebook_dict)
facebook_app = firebase_admin.initialize_app(cred_facebook, name="facebook")
db_facebook = firestore.client(facebook_app)

# =========================
# Firebase 2 (Makeo Media)
# =========================
cred_makeo_json = os.getenv("Makeoa_media")
cred_makeo_dict = json.loads(cred_makeo_json)

cred_Makeo_media = credentials.Certificate(cred_makeo_dict)
cred_Makeo_media_app = firebase_admin.initialize_app(
    cred_Makeo_media,
    name="cred_Makeo_media"
)
db_Makeo_media = firestore.client(cred_Makeo_media_app)

# ---------- GLOBAL ----------
bot_status_cache = False
bot_status_cache_new = False

authenticated_users = set()
active_users = set()

event_queue = queue.Queue()
app = None

# ---------- STREAM ----------
def fast_stream(batch=2000):
    query = db_facebook.collection(COLLECTION).limit(batch)
    while True:
        docs = list(query.stream())
        if not docs:
            break
        for d in docs:
            yield d
        query = db_facebook.collection(COLLECTION).start_after(docs[-1]).limit(batch)

# ---------- LISTENER ----------
def start_firestore_listener():
    doc_ref = db_Makeo_media.collection("Bot_Settings").document("Status")
    doc_ref_new = db_Makeo_media.collection("Telegram_bot_settings").document("Status")

    def on_snapshot(doc_snapshot, changes, read_time):
        global bot_status_cache
        for doc in doc_snapshot:
            data = doc.to_dict()
            if data and "Status" in data:
                bot_status_cache = bool(data["Status"])
                event_queue.put("status_changed")

    def on_snapshot_new(doc_snapshot, changes, read_time):
        global bot_status_cache_new
        for doc in doc_snapshot:
            data = doc.to_dict()
            if data and "Bot_status" in data:
                bot_status_cache_new = bool(data["Bot_status"])
                event_queue.put("status_changed")

    doc_ref.on_snapshot(on_snapshot)
    doc_ref_new.on_snapshot(on_snapshot_new)

# ---------- STATUS ----------
def get_bot_status():
    return bot_status_cache

def set_bot_status(value: bool):
    db_Makeo_media.collection("Bot_Settings").document("Status").set(
        {"Status": value}, merge=True
    )

def get_bot_status_new():
    return bot_status_cache_new

def set_bot_status_new(value: bool):
    db_Makeo_media.collection("Telegram_bot_settings").document("Status").set(
        {"Bot_status": value}, merge=True
    )

# ---------- KEYBOARD (FIXED STRUCTURE دائمًا ثابتة) ----------
def get_keyboard():
    status = get_bot_status()
    status_new = get_bot_status_new()

    toggle_text = "🟢 Bot ON" if status else "🔴 Bot OFF"
    toggle_text_new = "🟢 Bot2 ON" if status_new else "🔴 Bot2 OFF"

    keyboard = [
        ["📊 Statistics", "📊 Bot Stats"],
        ["📈 Activity Chart"],
        ["📁 Extract Data"],
        [toggle_text],
        [toggle_text_new]
    ]

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ---------- QUEUE ----------
async def queue_worker():
    while True:
        event = await asyncio.to_thread(event_queue.get)
        if event == "status_changed":
            for user_id in list(active_users):
                try:
                    await app.bot.send_message(
                        chat_id=user_id,
                        text="🔄 Updated",
                        reply_markup=get_keyboard()
                    )
                except:
                    pass

async def post_init(application):
    application.create_task(queue_worker())

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.id
    active_users.add(user)

    if user in authenticated_users:
        await update.message.reply_text("Welcome back", reply_markup=get_keyboard())
    else:
        await update.message.reply_text("Enter password:")

# ---------- STATS ----------
async def statistics():
    total = 0
    servers = Counter()

    for doc in fast_stream():
        data = doc.to_dict()
        total += 1
        servers[data.get("PrimarySource", "Unknown")] += 1

    msg = f"📊 Total Records: {total}\n\n"
    for s, c in servers.items():
        msg += f"{s}: {c}\n"

    return msg

async def bot_stats():
    doc = db_Makeo_media.collection("Bot_Settings").document("Statics").get()

    if doc.exists:
        data = doc.to_dict()
        work = data.get("Work", 0)
        failed = data.get("Failed", 0)
        banned = data.get("Banned", 0)
    else:
        work = failed = banned = 0

    total_failures = failed + banned
    total = work + total_failures

    success = (work / total * 100) if total else 0
    fail = (total_failures / total * 100) if total else 0

    return f"""
📊 Bot Statistics:

✅ Work: {work}
❌ Failed + Banned: {total_failures}

📈 Success: {success:.2f}%
📉 Failure: {fail:.2f}%
"""

# ---------- HANDLER ----------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.id
    text = update.message.text

    active_users.add(user)

    # AUTH
    if user not in authenticated_users:
        if text == PASSWORD:
            authenticated_users.add(user)
            await update.message.reply_text("✅ Authorized", reply_markup=get_keyboard())
        else:
            await update.message.reply_text("Wrong password")
        return

    # BOT1 TOGGLE
    if text in ["🟢 Bot ON", "🔴 Bot OFF"]:
        current = get_bot_status()
        set_bot_status(not current)
        await update.message.reply_text("Updated", reply_markup=get_keyboard())
        return

    # BOT2 TOGGLE (FIXED)
    if text in ["🟢 Bot2 ON", "🔴 Bot2 OFF"]:
        current = get_bot_status_new()
        set_bot_status_new(not current)
        await update.message.reply_text("Bot2 Updated", reply_markup=get_keyboard())
        return

    # OTHER
    if text == "📊 Statistics":
        await update.message.reply_text(await statistics(), reply_markup=get_keyboard())

    elif text == "📊 Bot Stats":
        await update.message.reply_text(await bot_stats(), reply_markup=get_keyboard())

    elif text == "📈 Activity Chart":
        await update.message.reply_text("Chart feature here", reply_markup=get_keyboard())

# ---------- MAIN ----------
app = (
    ApplicationBuilder()
    .token(BOT_TOKEN)
    .post_init(post_init)
    .build()
)

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

start_firestore_listener()

print("Bot running...")
app.run_polling()
