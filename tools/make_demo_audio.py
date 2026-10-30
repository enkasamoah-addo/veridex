"""Run ONCE when your Khaya quota is available:  python tools/make_demo_audio.py
Saves a fixed voice clip per language and verdict into voice_clips/, so the live demo never needs Khaya.
Usage: python tools/make_demo_audio.py            (all languages)
       python tools/make_demo_audio.py tw ga      (only some)"""
import os, sys, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import voice
TEXT = {
 "RED": "Danger. This looks like a scam. Do not send any money. Call the SEC on 0800 100 065 to report it.",
 "YELLOW": "Not sure. Please do not pay yet. Call the SEC on 0800 100 065 and ask if they are licensed.",
 "GREEN": "This company is on an official list. Still confirm with the SEC on 0800 100 065 before you pay.",
}
if not voice.available(): sys.exit("Set KHAYA_API_KEY first.")
langs = sys.argv[1:] or [k for k in voice.LANGS if k != "en"]
os.makedirs(voice.CLIPS, exist_ok=True)
for lang in langs:
    for level, en in TEXT.items():
        dest = os.path.join(voice.CLIPS, f"{lang}_{level}.ogg")
        if os.path.exists(dest): print("have", dest); continue
        txt, ok = voice.tr(en, lang)
        if not ok: print("translate failed", lang, level, voice.last_error); continue
        p = voice.speak(txt, lang)
        if p: shutil.copy(p, dest); print("saved", dest)
        else: print("tts failed", lang, level, voice.last_error)
m = voice.menu_voice()
if m: shutil.copy(m, os.path.join(voice.CLIPS, "menu.ogg")); print("saved menu.ogg")
print("Done. Commit voice_clips/ to git so every machine has the audio.")
