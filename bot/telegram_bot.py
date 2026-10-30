"""Veridex Telegram bot. Token from @BotFather:
  PowerShell:  $env:TELEGRAM_BOT_TOKEN="..." ; $env:KHAYA_API_KEY="..." ; python bot/telegram_bot.py"""
import os, sys, re, logging, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import env; env.load()
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from core import checker, voice
import db
logging.basicConfig(level=logging.INFO)
logging.getLogger('httpx').setLevel(logging.WARNING)  # httpx logs would print the bot token

WELCOME = ("👋 Welcome. I am Veridex. I check if an investment offer is safe.\n\n"
           "Send me (or forward) the message, company name or link you were given. You can also send a VOICE NOTE. "
           "I will tell you if it looks safe, and why, using the SEC's real warning and licence lists.\n\n"
           "Choose your language (I will read the answer out loud too):")
NOKEY = "⚠️ Local-language voice is not connected on this server yet (KHAYA_API_KEY missing), so I can only answer in English text."

def lang_kb():
    items = list(voice.LANGS.items())
    rows = [[InlineKeyboardButton(v[0], callback_data=f"lang:{k}") for k, v in items[i:i + 3]] for i in range(0, len(items), 3)]
    return InlineKeyboardMarkup(rows)

async def welcome(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(WELCOME, reply_markup=lang_kb())
    if not c.user_data.get("menu_sent"):
        ogg = next((os.path.join(voice.CLIPS, n) for n in ("menu.ogg", "menu.mp3", "menu.m4a") if os.path.exists(os.path.join(voice.CLIPS, n))), None)
        if not ogg and not voice.quota_hit(): ogg = voice.menu_voice()
        if ogg:
            c.user_data["menu_sent"] = True
            with open(ogg, "rb") as f: await u.message.reply_voice(f, caption="🔊 Listen, then tap your language")

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await welcome(u, c)

async def lang_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text("Choose your language:", reply_markup=lang_kb())

async def pick_lang(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    lang = q.data.split(":")[1]; c.user_data["lang"] = lang
    msg = f"✅ {voice.LANGS[lang][0]}. Now send me the offer you want checked: type it, forward it, or send a voice note."
    if lang != "en":
        if not voice.available(): msg += "\n\n" + NOKEY
        else: msg = f"✅ {voice.LANGS[lang][0]}.\n" + voice.translate("Now send me the offer you want checked. You can type it or send a voice note.", lang)
    await q.message.reply_text(msg)

async def toggle_voice(u: Update, c: ContextTypes.DEFAULT_TYPE):
    on = not c.user_data.get("voice_off", False)
    c.user_data["voice_off"] = on
    await u.message.reply_text("🔇 Voice replies OFF. Send /voice to turn on." if on else "🔊 Voice replies ON.")

LABELS = {"why": "Why:", "todo": "What to do now:"}

def localized_text(v, lang):
    """Whole verdict in the user's language. Each piece is translated separately and cached, so repeats cost no API calls.
    Returns (text, all_ok)."""
    if lang == "en": return checker.render(v), True
    oks = []
    def T(x):
        out, ok = voice.tr(x, lang); oks.append(ok); return out
    lines = [v.headline.split(" ", 1)[0] + " " + T(v.headline.split(" ", 1)[1]), ""]
    if v.checks:
        lines += [T("Our 6 checks:")] + [f"{i} {T(l)}" for i, l in v.checks] + [""]
    lines += [T(LABELS["why"])]
    lines += ["• " + T(r) for r in v.reasons[:4]]
    lines += ["", T(LABELS["todo"])] + [f"{i}. {T(d)}" for i, d in enumerate(v.do_now, 1)]
    lines += ["", T(v.comfort)]
    return "\n".join(lines), all(oks)

async def send_voice(u, c, v, lang):
    if c.user_data.get("voice_off"): return
    msg = u.effective_message
    spoken = checker.spoken(v)
    path = voice.clip_for(lang, v.level)                      # 1) human recording
    note = ""
    if not path and lang != "en":
        spoken_l, ok = voice.tr(spoken, lang)
        if ok and not voice.quota_hit(): path = voice.speak(spoken_l, lang)   # 2) Khaya
    elif not path and lang == "en":
        path = voice.speak(spoken, "en") if voice.available() and not voice.quota_hit() else None
        if not path: path = voice.speak_english_fallback(spoken)  # 3) English-only fallback
    if path:
        with open(path, "rb") as f: await msg.reply_voice(f)
    else:
        why = "the voice service has reached its limit" if voice.quota_hit() else "the voice service is not available right now"
        await msg.reply_text(f"🔇 Sorry, I cannot read this out loud right now ({why}). The written answer above is complete.")

async def answer(u: Update, c: ContextTypes.DEFAULT_TYPE, text: str, heard: str = ""):
    lang = c.user_data.get("lang", "en")
    v = checker.check(text)
    body, ok = localized_text(v, lang)
    c.user_data["last_en"] = checker.render(v)
    parts = ([heard] if heard else []) + [body]
    if lang != "en" and not ok:
        parts.append("⚠️ I could not translate all of this into " + voice.LANGS[lang][0] +
                     (" because the language service has reached its limit." if voice.quota_hit() else " right now.") + " Showing English for the missing parts.")
    cid = db.add_case("telegram_user", "telegram", str(u.effective_user.id), text[:500], v)
    if v.level == "RED" or (v.level == "YELLOW" and v.flags):
        parts.append("🕷️ To protect other people, this offer (never your name) has been passed to the SEC team. Our investigator, Ananse, is following it up.")
    rows = [[InlineKeyboardButton("🚨 Report this to the SEC", callback_data=f"report:{cid}")]]
    if lang != "en": rows.append([InlineKeyboardButton("🇬🇧 Show in English", callback_data="show_en")])
    await u.effective_message.reply_text("\n\n".join(parts), reply_markup=InlineKeyboardMarkup(rows))
    await send_voice(u, c, v, lang)

async def show_en(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    await q.message.reply_text(c.user_data.get("last_en", "Send me an offer first."))

GREET = re.compile(r"^\s*(hi+|hello+|hey+|hiya|yo|good\s*(morning|afternoon|evening)|morning|akwaaba|maakye|maaha|maadwo|ola|help|menu|start|test|testing)\W*$", re.I)
CHAT = re.compile(r"^\s*(thanks?( you)?|thank u|ok(ay)?|yes|no|nice|cool|great|hmm+|wow|me da wo ase|medaase)\W*$", re.I)

async def on_text(u: Update, c: ContextTypes.DEFAULT_TYPE):
    text = u.message.text or u.message.caption or ""
    lang = c.user_data.get("lang", "en")
    if GREET.match(text):
        await welcome(u, c); return
    if CHAT.match(text):
        await u.message.reply_text("You are welcome 🙏 Send me any investment offer, company name, link or voice note and I will check it for you. Stay safe!"); return
    if lang != "en" and voice.available():
        # user may type in their language: translate to English for the checker
        eng = voice.translate(text, lang, to_english=True)
        text = text + " " + eng if eng != text else text
    await answer(u, c, text)

async def on_voice(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not voice.available():
        await u.message.reply_text("I can't listen to voice notes yet on this server (KHAYA_API_KEY missing). Please type the message."); return
    lang = c.user_data.get("lang", "en")
    await u.message.reply_text("🎧 Listening...")
    f = await (u.message.voice or u.message.audio).get_file()
    path = os.path.join(tempfile.gettempdir(), f"vx_{u.message.message_id}.ogg")
    await f.download_to_drive(path)
    heard = voice.transcribe(path, lang)
    if not heard:
        await u.message.reply_text(f"Sorry, I could not understand that voice note. Please try again, speak slowly, or type it. ({voice.last_error[:120]})"); return
    eng = voice.translate(heard, lang, to_english=True) if lang != "en" else heard
    await answer(u, c, f"{heard} {eng}" if eng != heard else heard, heard=f'🎙 I heard: "{heard}"' + (f'\n(In English: "{eng}")' if eng != heard else ""))

async def report(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer("Sent to the SEC desk. Thank you.")
    cid = int(q.data.split(":")[1]); db.update(cid, status="reported_by_user")
    await q.message.reply_text("✅ Thank you. Your report is now with the SEC team. Do NOT pay these people. If you already paid, call your MoMo provider right now.")

async def on_error(update, context):
    err = context.error
    name = err.__class__.__name__
    if name in ("NetworkError", "TimedOut", "ConnectError"):
        print(f"[network] {name}: connection to Telegram dropped, retrying...")   # one quiet line, no traceback
    else:
        logging.exception("Unhandled error", exc_info=err)

def main():
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not tok: sys.exit('Set TELEGRAM_BOT_TOKEN. PowerShell: $env:TELEGRAM_BOT_TOKEN="..."')
    print("Khaya voice:", "ON" if voice.available() else "OFF (set KHAYA_API_KEY)")
    app = (Application.builder().token(tok)
           .connect_timeout(40).read_timeout(40).write_timeout(40).pool_timeout(40)
           .get_updates_connect_timeout(40).get_updates_read_timeout(40).get_updates_write_timeout(40).get_updates_pool_timeout(40)
           .build())
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("lang", lang_cmd))
    app.add_handler(CommandHandler("voice", toggle_voice))
    app.add_handler(CallbackQueryHandler(pick_lang, pattern="^lang:"))
    app.add_handler(CallbackQueryHandler(report, pattern="^report:"))
    app.add_handler(CallbackQueryHandler(show_en, pattern="^show_en$"))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    app.run_polling(bootstrap_retries=-1, drop_pending_updates=True)  # keep retrying on slow networks
if __name__ == "__main__": main()
