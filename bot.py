


import logging
import os
import json
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, ChatMemberHandler
)
from datetime import timezone

BOT_TOKEN = '8689327624:AAGMNVlhz3qu4wOS4Agbij_BhaVX6jj6Aho'
DATA_FILE = 'registered_chats.json'

ALLOWED_USERNAMES = {'SpammBotsss'}
BLOCKED_USER_IDS = {7784476578}

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        registered_chats = set(tuple(chat) for chat in json.load(f))
else:
    registered_chats = set()

user_data = {}
active_sessions = {i: False for i in range(1, 11)}
scheduled_jobs = {i: None for i in range(1, 11)}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return

    user_id = update.effective_user.id
    username = update.effective_user.username

    if user_id in BLOCKED_USER_IDS or (username and username not in ALLOWED_USERNAMES):
        await update.message.reply_text(
            "Ihr Zugang zu diesem Bot wurde widerrufen."
        )
        return

    await send_menu(update, context)

async def send_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    username = update.effective_user.username if update.effective_user else None

    if user_id in BLOCKED_USER_IDS or (username and username not in ALLOWED_USERNAMES):
        text = "Ihr Zugang zu diesem Bot wurde widerrufen."
        if update.callback_query:
            await update.callback_query.message.edit_text(text)
        else:
            await update.message.reply_text(text)
        return

    keyboard = []
    for i in range(1, 11, 2):
        row = [
            InlineKeyboardButton(
                f"Spam {i} {'✅' if active_sessions[i] else ''}",
                callback_data=f'spam_{i}'
            )
        ]
        if active_sessions[i]:
            row.append(InlineKeyboardButton(f"Stop {i}", callback_data=f'stop_{i}'))

        if i + 1 <= 10:
            row.append(
                InlineKeyboardButton(
                    f"Spam {i+1} {'✅' if active_sessions[i+1] else ''}",
                    callback_data=f'spam_{i+1}'
                )
            )
            if active_sessions[i+1]:
                row.append(
                    InlineKeyboardButton(f"Stop {i+1}", callback_data=f'stop_{i+1}')
                )

        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("📂 Chats ansehen", callback_data='view_chats')])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.edit_text(
            "📋 Wählen Sie eine Aktion:", reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "📋 Wählen Sie eine Aktion:", reply_markup=reply_markup
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    username = query.from_user.username

    if user_id in BLOCKED_USER_IDS or (username and username not in ALLOWED_USERNAMES):
        await query.message.edit_text("Ihr Zugang zu diesem Bot wurde widerrufen.")
        return

    if query.data.startswith('spam_'):
        session = int(query.data.split('_')[1])
        if active_sessions[session]:
            await query.message.reply_text(
                f"⚠️ Spam {session} ist bereits aktiv."
            )
        else:
            user_data[user_id] = {
                'state': 'awaiting_message',
                'session': session
            }
            await query.message.reply_text(
                f"✉️ Bitte senden Sie die Nachricht für Spam {session}."
            )
        await send_menu(update, context)

    elif query.data.startswith('stop_'):
        session = int(query.data.split('_')[1])
        if active_sessions[session]:
            if scheduled_jobs[session]:
                scheduled_jobs[session].schedule_removal()
                scheduled_jobs[session] = None
            active_sessions[session] = False
            await query.message.reply_text(f"🛑 Spam {session} wurde gestoppt.")
        else:
            await query.message.reply_text(f"❌ Spam {session} ist nicht aktiv.")
        await send_menu(update, context)

    elif query.data == 'view_chats':
        if registered_chats:
            chat_list = '\n'.join(
                [f"{title} ({cid})" for cid, title in registered_chats]
            )
            await query.message.reply_text(
                f"📂 Der Bot ist in folgenden Chats:\n{chat_list}"
            )
        else:
            await query.message.reply_text("🚫 Keine registrierten Chats.")

async def receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.message.from_user.username

    if user_id in BLOCKED_USER_IDS or (username and username not in ALLOWED_USERNAMES):
        await update.message.reply_text("Ihr Zugang wurde widerrufen.")
        return

    if user_id in user_data and user_data[user_id]['state'] == 'awaiting_message':
        session = user_data[user_id]['session']
        message_to_forward = update.message

        if not registered_chats:
            await update.message.reply_text("🚫 Keine Chats vorhanden.")
            user_data[user_id]['state'] = None
            return

        job = context.job_queue.run_repeating(
            send_scheduled_message,
            interval=10 * 60,
            first=(session - 1) * 60,
            data={
                'message': message_to_forward,
                'chats': registered_chats,
                'session': session
            }
        )

        scheduled_jobs[session] = job
        active_sessions[session] = True

        await update.message.reply_text(
            f"📤 Spam {session} gestartet."
        )

        user_data[user_id]['state'] = None
        await send_menu(update, context)

async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    message = job_data['message']
    chats = job_data['chats']
    session = job_data['session']

    from_chat_id = message.chat_id
    message_id = message.message_id

    logging.info(f"Spam {session} – Versand startet")

    for chat_id, chat_title in chats:
        try:
            await context.bot.forward_message(
                chat_id=chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id
            )
            logging.info(f"Gesendet an {chat_title} ({chat_id})")
            await asyncio.sleep(1.5)
        except Exception as e:
            logging.error(f"Fehler bei {chat_title} ({chat_id}): {e}")

async def my_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    chat = result.chat
    chat_id = chat.id
    chat_title = chat.title or chat.username or str(chat.id)

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    if old_status in ['left', 'kicked'] and new_status in ['member', 'administrator']:
        registered_chats.add((chat_id, chat_title))
        save_registered_chats()
    elif new_status in ['left', 'kicked']:
        registered_chats.discard((chat_id, chat_title))
        save_registered_chats()

def save_registered_chats():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(registered_chats), f, ensure_ascii=False)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    await update.message.reply_text(
        "/start – Start\n/help – Hilfe"
    )

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(ChatMemberHandler(
        my_chat_member_handler,
        ChatMemberHandler.MY_CHAT_MEMBER
    ))
    app.add_handler(
        MessageHandler(
            filters.ALL & filters.ChatType.PRIVATE & (~filters.COMMAND),
            receive_message
        )
    )

    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
