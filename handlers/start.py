#start.py

from telegram import Update
from telegram.ext import CallbackContext

def start(update: Update, context: CallbackContext):
    """/start: registra la chat e conferma."""
    cid = update.effective_chat.id
    CHAT_IDS.add(cid)
    salva_chat_ids()
    logging.info(f"Nuovo chat_id: {cid}")
    update.message.reply_text("Bot attivo. Ti invierò i reminder per lo studio.")
