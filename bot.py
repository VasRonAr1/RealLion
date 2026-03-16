
import logging
import os
import json
import asyncio
import random
import time

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ChatMemberHandler,
)
from telegram.error import RetryAfter, BadRequest, Forbidden

# ================== НАСТРОЙКИ ==================
BOT_TOKEN = os.getenv("BOT_TOKEN") or '8689327624:AAGMNVlhz3qu4wOS4Agbij_BhaVX6jj6Aho'
DATA_FILE = "registered_chats.json"

ALLOWED_USERNAMES = {"SpammBotsss", "patrickost", "Beckenbauer089"}  # без @
# ===============================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ================== ACCESS ==================
def is_allowed(update: Update) -> bool:
    user = update.effective_user
    if not user or not user.username:
        return False
    return user.username in ALLOWED_USERNAMES

# ================== DATA ==================
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        registered_chats = list(json.load(f))
else:
    registered_chats = []

messages_cycle = []
spam_task: asyncio.Task | None = None
flood_until = {}
msg_index = 0

FATAL_ERRORS = (
    "Chat not found",
    "Chat_restricted",
    "not enough rights",
    "Forbidden",
)

# ================== ERROR HANDLER ==================
async def error_handler(update, context):
    logging.error("Unhandled exception", exc_info=context.error)

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await send_menu(update)

# ================== MENU ==================
async def send_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("▶️ Start Spam", callback_data="start_spam")],
        [InlineKeyboardButton("⏹ Stop Spam", callback_data="stop_spam")],
    ]
    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.edit_text(
            "Aktion wählen:", reply_markup=markup
        )
    else:
        await update.message.reply_text(
            "Aktion wählen:", reply_markup=markup
        )

# ================== BUTTONS ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global spam_task

    query = update.callback_query

    if not is_allowed(update):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return

    await query.answer()

    if query.data == "start_spam":
        if spam_task and not spam_task.done():
            await query.message.reply_text("Spam ist schon an.")
            return

        messages_cycle.clear()
        context.user_data["await_msgs"] = 5  # теперь 5 сообщений
        await query.message.reply_text("Schiken Sie mir 5 Nachrichten.")

    elif query.data == "stop_spam":
        if spam_task:
            spam_task.cancel()
            spam_task = None
            await query.message.reply_text("Spam ist aus")
        else:
            await query.message.reply_text("Spam ist nicht an.")

# ================== RECEIVE MSG ==================
async def receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global spam_task

    if not is_allowed(update):
        return

    if update.message.media_group_id:
        await update.message.reply_text("Альбомы не поддерживаются.")
        return

    if context.user_data.get("await_msgs", 0) > 0:
        messages_cycle.append(update.message)
        context.user_data["await_msgs"] -= 1

        if context.user_data["await_msgs"] == 0:
            spam_task = asyncio.create_task(spam_loop(context))
            await update.message.reply_text("Spam an.")
        else:
            await update.message.reply_text(
                f"Осталось сообщений: {context.user_data['await_msgs']}"
            )

# ================== SEND MESSAGE ==================
async def send_any(bot, chat_id, msg):
    if msg.text:
        await bot.send_message(chat_id, msg.text)

    elif msg.photo:
        await bot.send_photo(
            chat_id,
            msg.photo[-1].file_id,
            caption=msg.caption
        )

    elif msg.video:
        await bot.send_video(
            chat_id,
            msg.video.file_id,
            caption=msg.caption
        )

# ================== SPAM LOOP ==================
async def spam_loop(context: ContextTypes.DEFAULT_TYPE):
    global msg_index, spam_task

    logging.info("Spam loop started")

    try:
        start_cycle_time = time.time()

        while True:
            if not messages_cycle:
                logging.warning("messages_cycle пуст, жду...")
                await asyncio.sleep(5)
                continue

            for chat_id, chat_title in list(registered_chats):
                now = time.time()

                if chat_id in flood_until and flood_until[chat_id] > now:
                    continue

                msg = messages_cycle[msg_index % len(messages_cycle)]
                msg_index += 1

                try:
                    await send_any(context.bot, chat_id, msg)
                    logging.info(f"Отправлено в {chat_title}")

                except RetryAfter as e:
                    flood_until[chat_id] = time.time() + e.retry_after
                    logging.warning(f"FloodWait {chat_title}: {e.retry_after}s")

                except (BadRequest, Forbidden) as e:
                    err = str(e)
                    logging.error(f"{chat_title}: {err}")

                    if any(x in err for x in FATAL_ERRORS):
                        registered_chats[:] = [
                            c for c in registered_chats if c[0] != chat_id
                        ]
                        save_chats()

                await asyncio.sleep(random.uniform(4, 7))

            if time.time() - start_cycle_time >= 600:
                logging.info("Глобальная пауза 60s")
                await asyncio.sleep(60)
                start_cycle_time = time.time()

    except asyncio.CancelledError:
        logging.warning("Spam loop cancelled")
        raise

    except Exception:
        logging.exception("Spam loop crashed, restarting")
        spam_task = asyncio.create_task(spam_loop(context))

# ================== WATCHDOG ==================
async def watchdog():
    while True:
        logging.info("Bot alive")
        await asyncio.sleep(300)

async def post_init(app):
    app.create_task(watchdog())

# ================== CHAT TRACK ==================
async def my_chat_member_handler(update: Update, context):
    chat = update.my_chat_member.chat
    chat_id = chat.id
    chat_title = chat.title or str(chat.id)

    status = update.my_chat_member.new_chat_member.status

    if status in ("member", "administrator"):
        if [chat_id, chat_title] not in registered_chats:
            registered_chats.append([chat_id, chat_title])
            save_chats()
    else:
        registered_chats[:] = [c for c in registered_chats if c[0] != chat_id]
        save_chats()

def save_chats():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(registered_chats, f, ensure_ascii=False)

# ================== MAIN ==================
def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(
        MessageHandler(filters.ChatType.PRIVATE & (~filters.COMMAND), receive_message)
    )
    app.add_handler(
        ChatMemberHandler(my_chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER)
    )

    app.add_error_handler(error_handler)
    app.run_polling()

if __name__ == "__main__":
    main()







