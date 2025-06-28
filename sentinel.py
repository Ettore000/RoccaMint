from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, Dispatcher, CallbackQueryHandler
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from pytz import timezone
import time
import logging
import json
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import re

# per tenere in memoria l’ultima riga proposta per annullamento
pending_annulla = {}  # chat_id -> line_text

# file dove salvo i conteggi di timeout per ogni chat
MISSES_FILE = "misses.json"

# carico (o inizializzo) il contatore di “missed prompts”
if os.path.exists(MISSES_FILE):
    with open(MISSES_FILE, "r", encoding="utf-8") as f:
        misses = json.load(f)
else:
    misses = {}   # chat_id (str) -> int

# ─── Configurazione logging ─────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ─── Caricamento token & init Bot + Scheduler ──────────────────────────────────
with open("token.txt", "r") as f:
    TOKEN = f.read().strip()
logging.info("Token caricato correttamente.")

bot = Bot(token=TOKEN)
scheduler = BackgroundScheduler()

# ─── Percorsi e costanti ────────────────────────────────────────────────────────
CHAT_IDS_FILE = "chat_ids.json"
REPORT_DIR    = "report_settimanali"
DAILY_DIR     = "report_giornalieri"
WEEKDAYS      = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]

os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(DAILY_DIR, exist_ok=True)

# ─── Stato in memoria dei poll aperti ───────────────────────────────────────────
pending_poll_message = {}  # chat_id -> message_id

# ─── Caricamento chat_id esistenti ─────────────────────────────────────────────
if os.path.exists(CHAT_IDS_FILE):
    with open(CHAT_IDS_FILE, "r", encoding="utf-8") as f:
        CHAT_IDS = set(json.load(f))
    logging.info("Chat ID caricati da file.")
else:
    CHAT_IDS = set()

def salva_chat_ids():
    """Salva su file se la lista di chat_id è cambiata."""
    try:
        if os.path.exists(CHAT_IDS_FILE):
            with open(CHAT_IDS_FILE, "r", encoding="utf-8") as f:
                old = set(json.load(f))
            if old == CHAT_IDS:
                return
        with open(CHAT_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(CHAT_IDS), f)
        logging.info("Chat ID salvati su file.")
    except Exception as e:
        logging.error(f"Errore salvataggio chat_id: {e}")

def carica_piano_studio():
    """Ritorna la lista di (orario, testo) dal piano corrente."""
    stato_file = "sentinel_piano_corrente.json"
    modalità = "normale"
    if os.path.exists(stato_file):
        try:
            with open(stato_file, "r", encoding="utf-8") as f:
                dati = json.load(f)
            modalità = dati.get("modalità", "normale")
        except Exception as e:
            logging.warning(f"Stato piano corrotto ({e}), uso 'normale'.")
    nome_file = f"piano_{modalità}.json"
    if not os.path.exists(nome_file):
        nome_file = "piano_normale.json"
    try:
        with open(nome_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"Errore caricamento {nome_file}: {e}")
        return []
    raw = data.get("blocchi") if isinstance(data, dict) else data if isinstance(data, list) else []
    piano = []
    for entry in raw:
        if isinstance(entry, list) and len(entry) == 2:
            piano.append((entry[0], entry[1]))
        elif isinstance(entry, dict):
            o = entry.get("ora"); t = entry.get("testo")
            if o and t:
                piano.append((o, t))
    return piano

def start(update: Update, context: CallbackContext):
    """/start: registra la chat e conferma."""
    cid = update.effective_chat.id
    CHAT_IDS.add(cid)
    salva_chat_ids()
    logging.info(f"Nuovo chat_id: {cid}")
    update.message.reply_text("Bot attivo. Ti invierò i reminder per lo studio.")

def manda_reminder(orario, messaggio):
    """Invia il reminder, mostra attività successiva e chiede Sì/No."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    piano = carica_piano_studio()
    idx = next((i for i,(o,_) in enumerate(piano) if o == orario), None)
    if idx is not None and idx+1 < len(piano):
        po, pt = piano[idx+1]
        testo = f"{messaggio}\n\n⏳ Hai tempo fino alle *{po}*, poi *{pt}*."
    else:
        testo = messaggio

    for cid in CHAT_IDS:
        sent = bot.send_message(chat_id=cid, text=testo, parse_mode='Markdown')
        with open("sentinel_log.txt","a",encoding="utf-8") as lg:
            lg.write(f"{now} - chat_id: {cid} - reminder: {messaggio}\n")
        if "Studio" in messaggio:
            poll = bot.send_message(
                chat_id=cid,
                text="Stai studiando?",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Sì", callback_data="scoring_si"),
                    InlineKeyboardButton("No", callback_data="scoring_no")
                ]])
            )
            pending_poll_message[cid] = poll.message_id

def risposta_scoring(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()

    cid = q.message.chat.id
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resp = q.data.split("_")[1]  # "si" o "no"

    # —–––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
    # 1) resetto il contatore dei miss per questa chat (se esiste)
    key = str(cid)
    if key in misses:
        misses.pop(key)
        with open(MISSES_FILE, "w", encoding="utf-8") as f:
            json.dump(misses, f)
    # —–––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––

    # 2) registro i minuti (30 o 0)
    minuti = 30 if resp == "si" else 0
    with open("sentinel_studio_log.txt", "a", encoding="utf-8") as lg:
        lg.write(f"{now} - chat_id: {cid} - minuti_studio: {minuti}\n")

    # 3) aggiorno il messaggio Telegram
    q.edit_message_text(text=f"Risposta registrata: {resp.upper()}")

    verifica_proposta_adattamento(cid)

def verifica_proposta_adattamento(chat_id):
    """Se 3 blocchi a zero in giornata, propone piano più leggero."""
    oggi = datetime.now().strftime("%Y-%m-%d")
    cnt = 0
    if os.path.exists("sentinel_studio_log.txt"):
        with open("sentinel_studio_log.txt","r",encoding="utf-8") as f:
            lines = [l for l in f if oggi in l and f"chat_id: {chat_id}" in l]
        for l in reversed(lines):
            if "minuti_studio: 0" in l:
                cnt += 1
            else:
                break
    if cnt >= 3:
        bot.send_message(
            chat_id=chat_id,
            text="3 blocchi vuoti! Vuoi un piano più leggero domani?",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Sì", callback_data="adatta_si"),
                InlineKeyboardButton("No", callback_data="adatta_no")
            ]])
        )

def risposta_adattamento(update: Update, context: CallbackContext):
    """Gestisce la scelta di adattare il piano dopo proposta."""
    q = update.callback_query; q.answer()
    cid = q.message.chat.id
    stato = {"modalità": "normale"}
    if os.path.exists("sentinel_piano_corrente.json"):
        with open("sentinel_piano_corrente.json","r",encoding="utf-8") as f:
            stato = json.load(f)
    mod = stato.get("modalità","normale")
    nuovo = {"normale":"ridotto","ridotto":"superridotto"}.get(mod,"superridotto")
    if q.data == "adatta_si":
        with open("sentinel_piano_corrente.json","w",encoding="utf-8") as f:
            json.dump({"modalità":nuovo}, f)
        bot.send_message(chat_id=cid, text=f"Piano cambiato a {nuovo.upper()} ✔️")
    else:
        bot.send_message(chat_id=cid, text="Manteniamo piano attuale ✔️")

def genera_grafico_settimanale():
    log_file = "sentinel_studio_log.txt"
    if not os.path.exists(log_file):
        logging.info("Nessun log di studio per grafico settimanale.")
        return

    now = datetime.now(timezone('Europe/Rome'))
    start = now - timedelta(days=6)

    # inizializzo contatore per ciascun giorno della settimana (0=Lun ... 6=Dom)
    giorni_tot = {i: 0 for i in range(7)}
    total_minuti = 0

    pattern = re.compile(
        r'^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - chat_id: \d+ - minuti_studio: (?P<min>\d+)$'
    )

    with open(log_file, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            m = pattern.match(line)
            if not m:
                continue

            ts_str = m.group('ts')
            minuti = int(m.group('min'))

            try:
                dt_naive = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                dt = timezone('Europe/Rome').localize(dt_naive)
            except ValueError:
                continue

            if not (start <= dt <= now):
                continue

            wd = dt.weekday()  # 0=Lun ... 6=Dom
            giorni_tot[wd] += minuti
            total_minuti += minuti

    if total_minuti == 0:
        logging.info("Nessun dato utile (tutti 0) per grafico settimanale.")
        return

    # preparo etichette e valori in ore
    labels = WEEKDAYS
    vals = [giorni_tot[i] / 60 for i in range(7)]

    # disegno a line plot
    plt.figure(figsize=(10, 6))
    plt.plot(range(7), vals, marker="o", linestyle="-")
    plt.xticks(range(7), labels)
    plt.xlabel("Giorno della settimana")
    plt.ylabel("Ore di studio")
    plt.title("Andamento settimanale studio (ultimi 7 giorni)")
    plt.grid(alpha=0.3)
    plt.tight_layout()

    # salva in report_settimanali/
    date_str = now.strftime("%Y-%m-%d")
    out_file = os.path.join(REPORT_DIR, f"grafico_settimanale_{date_str}.png")
    plt.savefig(out_file)
    plt.close()

    # calcolo totale ore/minuti settimanali
    ore, minuti = divmod(total_minuti, 60)
    caption = f"📊 Ultimi 7 giorni: hai studiato **{ore}h {minuti}m**"

    # invio
    for cid in CHAT_IDS:
        try:
            with open(out_file, "rb") as img:
                bot.send_photo(
                    chat_id=cid,
                    photo=img,
                    caption=caption,
                    parse_mode='Markdown'
                )
        except Exception as e:
            logging.error(f"Errore inviando grafico settimanale a {cid}: {e}")


def genera_grafico_giornaliero():
    log_file = "sentinel_studio_log.txt"
    if not os.path.exists(log_file):
        logging.info("Nessun log di studio trovato per il grafico giornaliero.")
        return

    oggi = datetime.now(timezone('Europe/Rome')).strftime("%Y-%m-%d")
    # inizializzo tutti gli 0-23 a 0 minuti
    ore_dict = {h: 0 for h in range(24)}
    total_minuti = 0

    # leggo il log e sommo i minuti nell'ora giusta
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.startswith(oggi):
                continue
            # "YYYY-MM-DD HH:MM:SS - chat_id: xxx - minuti_studio: yy"
            ts_str, _, rest = line.partition(" - chat_id")
            dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            minuti = int(rest.split(":")[-1])
            ore_dict[dt.hour] += minuti
            total_minuti += minuti

    if total_minuti == 0:
        logging.info("Nessuna attività di studio rilevata oggi.")
        return

    # prepara dati per il plot
    hours = list(ore_dict.keys())            # [0,1,2,...,23]
    values = [ore_dict[h] for h in hours]    # minuti cumulati in quell’ora

    # disegno
    plt.figure(figsize=(10, 5))
    plt.plot(hours, values, marker="o", linestyle="-")
    plt.xticks(hours)
    plt.xlabel("Ora del giorno")
    plt.ylabel("Minuti di studio")
    plt.title(f"Studio oggi ({oggi}) per fasce orarie")
    plt.grid(alpha=0.3)
    plt.tight_layout()

    # salva in report_giornalieri/
    grafico = os.path.join(DAILY_DIR, f"grafico_giornaliero_{oggi}.png")
    plt.savefig(grafico)
    plt.close()
    logging.info(f"Grafico giornaliero salvato in {grafico}")

    # calcolo totale ore/minuti
    ore, minuti = divmod(total_minuti, 60)
    caption = f"📈 Oggi hai studiato **{ore}h {minuti}m**"

    # mando a tutti i chat_id
    for cid in CHAT_IDS:
        try:
            with open(grafico, "rb") as img:
                bot.send_photo(
                    chat_id=cid,
                    photo=img,
                    caption=caption,
                    parse_mode='Markdown'
                )
        except Exception as e:
            logging.error(f"Errore inviando grafico giornaliero a {cid}: {e}")


def controllo_meta_giornata():
    """Alle 12:00: avvisa se hai già studiato o no entro metà giornata."""
    oggi = datetime.now().strftime("%Y-%m-%d")
    tot = 0
    if os.path.exists("sentinel_studio_log.txt"):
        with open("sentinel_studio_log.txt","r",encoding="utf-8") as f:
            for line in f:
                if not line.startswith(oggi): continue
                minuti = int(line.strip().split(" - ")[2].replace("minuti_studio: ",""))
                tot += minuti
    h, m = divmod(tot, 60)
    for cid in CHAT_IDS:
        if tot>0:
            testo = f"⏰ È già passata metà giornata e tu hai studiato {h}h {m}m."
        else:
            testo = "⏰ È già passata metà giornata e non hai ancora studiato! 😱"
        bot.send_message(chat_id=cid, text=testo)

def ferma(update: Update, context: CallbackContext):
    cid = update.effective_chat.id
    if cid in CHAT_IDS:
        CHAT_IDS.remove(cid)
        salva_chat_ids()
        update.message.reply_text(
            "✅ Reminder interrotti.  Usa /riprendi per riattivarli."
        )
    else:
        update.message.reply_text("I reminder erano già interrotti.")

def riprendi(update: Update, context: CallbackContext):
    cid = update.effective_chat.id
    if cid not in CHAT_IDS:
        CHAT_IDS.add(cid)
        salva_chat_ids()
        update.message.reply_text("✅ Reminder riattivati.")
    else:
        update.message.reply_text("I reminder erano già attivi.")

def annulla(update: Update, context: CallbackContext):
    cid = update.effective_chat.id
    if not os.path.exists("sentinel_studio_log.txt"):
        update.message.reply_text("Nessuna registrazione da annullare.")
        return

    # leggo tutte le righe e filtro per questa chat
    with open("sentinel_studio_log.txt", "r", encoding="utf-8") as f:
        lines = [l for l in f if f"chat_id: {cid}" in l]
    if not lines:
        update.message.reply_text("Nessuna registrazione da annullare.")
        return

    last = lines[-1].strip()
    pending_annulla[cid] = last

    kb = [
        [ InlineKeyboardButton("Sì", callback_data="annulla_si"),
          InlineKeyboardButton("No", callback_data="annulla_no") ]
    ]
    update.message.reply_text(
        f"Confermi di cancellare questa registrazione?\n`{last}`",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

def risposta_annulla(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()
    cid = q.message.chat.id
    data = q.data  # "annulla_si" o "annulla_no"

    if cid not in pending_annulla:
        q.edit_message_text("Nessuna operazione in sospeso.")
        return

    line_to_remove = pending_annulla.pop(cid)

    if data == "annulla_si":
        # rimuovo la prima occorrenza di quella riga
        with open("sentinel_studio_log.txt", "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        with open("sentinel_studio_log.txt", "w", encoding="utf-8") as f:
            removed = False
            for l in all_lines:
                if not removed and l.strip() == line_to_remove:
                    removed = True
                    continue
                f.write(l)
        q.edit_message_text(f"🗑️ Registrazione cancellata:\n`{line_to_remove}`", parse_mode="Markdown")
    else:
        q.edit_message_text("❌ Annullamento operazione.")


def test_settimanale(update: Update, context: CallbackContext):
    logging.info("Ricevuto /test_settimanale, genero grafico settimanale")
    genera_grafico_settimanale()
    update.message.reply_text(f"✅ Grafico settimanale GENERATO (cartella {REPORT_DIR}/).")

def status(update: Update, context: CallbackContext):
    cid = update.effective_chat.id
    oggi = datetime.now().strftime("%Y-%m-%d")
    tot = 0
    if os.path.exists("sentinel_studio_log.txt"):
        with open("sentinel_studio_log.txt","r",encoding="utf-8") as f:
            for l in f:
                if oggi in l and f"chat_id: {cid}" in l:
                    tot += int(l.strip().split(" - ")[2].replace("minuti_studio: ",""))
    h, m = divmod(tot, 60)
    if tot==0:
        update.message.reply_text("Oggi non hai studiato nulla. 🥲")
    else:
        update.message.reply_text(f"Hai studiato {h}h {m}m oggi. 📚")

def attuale(update: Update, context: CallbackContext):
    ora_corr = datetime.now(timezone('Europe/Rome'))
    hhmm = ora_corr.strftime("%H:%M")
    piano = carica_piano_studio()

    current = None
    next_ev = None

    for idx, (ora, testo) in enumerate(piano):
        h, m = map(int, ora.split(":"))
        ev_time = ora_corr.replace(hour=h, minute=m, second=0, microsecond=0)

        if ora_corr >= ev_time:
            current = (ora, testo)
        elif ora_corr < ev_time and next_ev is None:
            next_ev = (ora, testo)
            break

    if current:
        msg = f"Sono le *{hhmm}* — in corso: _{current[1]}_"
        if next_ev:
            msg += f"\n\n⏳ *Prossimo* alle *{next_ev[0]}*: _{next_ev[1]}_"
    else:
        if next_ev:
            msg = f"Sono le *{hhmm}* — ancora nessun blocco iniziato.\n\n⏳ *Prossimo* alle *{next_ev[0]}*: _{next_ev[1]}_"
        else:
            msg = f"Sono le *{hhmm}* — non ci sono blocchi programmati per oggi."

    update.message.reply_text(msg, parse_mode='Markdown')


def aggiungi(update: Update, context: CallbackContext):
    cid = update.effective_chat.id
    args = context.args
    if not args or not args[0].isdigit():
        update.message.reply_text("Uso: /aggiungi <minuti> — es. /aggiungi 20")
        return
    minuti = int(args[0])
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("sentinel_studio_log.txt","a",encoding="utf-8") as f:
        f.write(f"{now} - chat_id: {cid} - minuti_studio: {minuti}\n")
    update.message.reply_text(f"👍 Aggiunti manualmente {minuti} minuti di studio.")

def piano(update: Update, context: CallbackContext):
    """/piano <normale|ridotto|superridotto>"""
    cid = update.effective_chat.id
    if not context.args or context.args[0] not in ("normale", "ridotto", "superridotto"):
        update.message.reply_text(
            "Uso: /piano normale|ridotto|superridotto"
        )
        return
    nuovo = context.args[0]
    with open("sentinel_piano_corrente.json", "w", encoding="utf-8") as f:
        json.dump({"modalità": nuovo}, f)
    update.message.reply_text(f"Piano impostato su *{nuovo.upper()}*", parse_mode="Markdown")

# ─── Schedulazioni ──────────────────────────────────────────────────────────────
scheduler.add_job(genera_grafico_settimanale, 'cron', day_of_week='sun', hour=23, minute=50, timezone='Europe/Rome')
scheduler.add_job(genera_grafico_giornaliero, 'cron', hour=22, minute=0, timezone='Europe/Rome')
scheduler.add_job(controllo_meta_giornata,    'cron', hour=12, minute=0, timezone='Europe/Rome')
scheduler.start()

# ─── Pianifica reminder giornalieri ─────────────────────────────────────────────
for o,t in carica_piano_studio():
    h, m = map(int, o.split(":"))
    scheduler.add_job(manda_reminder, 'cron',
                      hour=h, minute=m,
                      timezone='Europe/Rome',
                      args=[o, t])

# ─── Handler Telegram ──────────────────────────────────────────────────────────
updater = Updater(TOKEN, use_context=True)
dp: Dispatcher = updater.dispatcher

dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("status", status))
dp.add_handler(CommandHandler("attuale", attuale))
dp.add_handler(CommandHandler("aggiungi", aggiungi))
dp.add_handler(CommandHandler("test_settimanale", test_settimanale))
dp.add_handler(CommandHandler("ferma", ferma))
dp.add_handler(CommandHandler("riprendi", riprendi))
dp.add_handler(CommandHandler("annulla", annulla))
dp.add_handler(CommandHandler("piano", piano))
dp.add_handler(CallbackQueryHandler(risposta_annulla, pattern="^annulla_"))
dp.add_handler(CallbackQueryHandler(risposta_scoring, pattern="^scoring_"))
dp.add_handler(CallbackQueryHandler(risposta_adattamento, pattern="^adatta_"))

updater.start_polling()
try:
    while True:
        time.sleep(1)
except (KeyboardInterrupt, SystemExit):
    scheduler.shutdown()
