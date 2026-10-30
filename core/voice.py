"""Local-language text + voice via Khaya (translation.ghananlp.org). Needs KHAYA_API_KEY.
Codes verified against khaya-sdk languages page (Oct 2026). Ghanaian Pidgin is NOT supported by Khaya."""
import os, io, json, wave, hashlib, subprocess, tempfile
import imageio_ffmpeg

# key: (label, translate pair to-lang, translate pair from-lang, asr code, tts code)
LANGS = {
    "en":  ("English", None, None, "eng", "eng"),
    "tw":  ("Twi", "en-tw", "tw-en", "twi", "twi"),
    "ga":  ("Ga", "en-gaa", "gaa-en", "gaa", "gaa"),
    "ee":  ("Ewe", "en-ee", "ee-en", "ewe", "ewe"),
    "fat": ("Fante", "en-fat", "fat-en", "fat", "fat"),
    "dag": ("Dagbani", "en-dag", "dag-en", "dag", "dag"),
}
ROOT = os.path.join(os.path.dirname(__file__), "..")
CACHE = os.path.join(ROOT, "audio_cache"); os.makedirs(CACHE, exist_ok=True)
TCACHE_FILE = os.path.join(CACHE, "translations.json")
try: _T = json.load(open(TCACHE_FILE, encoding="utf-8"))
except Exception: _T = {}
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
last_error = ""
CLIPS = os.path.join(ROOT, "voice_clips")  # put human recordings here: tw_RED.ogg, ga_YELLOW.ogg, en_GREEN.ogg, menu.ogg

def available(): return bool(os.environ.get("KHAYA_API_KEY"))
def _client():
    from khaya import KhayaClient
    return KhayaClient(os.environ["KHAYA_API_KEY"])

def translate(text, lang, to_english=False):
    """English -> lang (default) or lang -> English. Returns original text if it fails."""
    global last_error
    if lang == "en" or not available() or not text.strip(): return text
    pair = LANGS[lang][2 if to_english else 1]
    k = f"{pair}|{text}"
    if k in _T: return _T[k]
    try:
        with _client() as c:
            out = c.translate(text, pair).text
        _T[k] = out; json.dump(_T, open(TCACHE_FILE, "w", encoding="utf-8"), ensure_ascii=False)
        return out
    except Exception as e:
        last_error = f"translate: {e}"; print(last_error); return text

def _chunks(text, n=220):
    parts, cur = [], ""
    for s in text.replace("\n", " ").split(". "):
        s = s.strip()
        if not s: continue
        if len(cur) + len(s) + 2 > n and cur: parts.append(cur); cur = s
        else: cur = (cur + ". " + s) if cur else s
    if cur: parts.append(cur)
    return parts or [text]

def wav_to_ogg(wav_path):
    ogg = wav_path[:-4] + ".ogg"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", wav_path, "-c:a", "libopus", "-b:a", "32k", ogg], check=True)
    return ogg

def _to_ogg(wav_paths, ogg):
    """Any-format WAV chunks (incl. float32) -> one Opus .ogg via ffmpeg."""
    cmd = [FFMPEG, "-y", "-loglevel", "error"]
    for w in wav_paths: cmd += ["-i", w]
    if len(wav_paths) == 1:
        cmd += ["-ar", "24000", "-ac", "1", "-c:a", "libopus", "-b:a", "32k", ogg]
    else:
        inp = "".join(f"[{i}:a]aresample=24000,aformat=channel_layouts=mono[a{i}];" for i in range(len(wav_paths)))
        cat = "".join(f"[a{i}]" for i in range(len(wav_paths))) + f"concat=n={len(wav_paths)}:v=0:a=1[out]"
        cmd += ["-filter_complex", inp + cat, "-map", "[out]", "-c:a", "libopus", "-b:a", "32k", ogg]
    subprocess.run(cmd, check=True)

def speak(text, lang):
    """Text (already in `lang`) -> path to .ogg (Opus) voice note, or None."""
    global last_error
    if not available() or not text.strip(): return None
    base = os.path.join(CACHE, f"{lang}_{hashlib.md5(text.encode()).hexdigest()}")
    if os.path.exists(base + ".ogg"): return base + ".ogg"
    try:
        paths = []
        with _client() as c:
            for i, part in enumerate(_chunks(text)):
                p = f"{base}_{i}.wav"
                open(p, "wb").write(c.synthesize(part, LANGS[lang][4]).audio)
                paths.append(p)
        _to_ogg(paths, base + ".ogg")
        return base + ".ogg"
    except Exception as e:
        last_error = f"tts: {e}"; print(last_error); return None

def transcribe(audio_path, lang):
    """Telegram voice (.ogg) -> text in `lang`. Returns None on failure."""
    global last_error
    if not available(): return None
    try:
        wav = audio_path.rsplit(".", 1)[0] + "_16k.wav"
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", audio_path, "-ar", "16000", "-ac", "1", wav], check=True)
        with _client() as c:
            return c.transcribe(wav, LANGS[lang][3]).text
    except Exception as e:
        last_error = f"asr: {e}"; print(last_error); return None

def menu_voice():
    """One voice note greeting in every language: 'Welcome to Veridex. To continue in X, tap X.'
    Built once, then cached on disk. Returns .ogg path or None."""
    global last_error
    if not available(): return None
    ogg = os.path.join(CACHE, "menu.ogg")
    if os.path.exists(ogg): return ogg
    try:
        paths = []
        with _client() as c:
            for k, (label, *_rest) in LANGS.items():
                en = f"Welcome to Veridex. To continue in {label}, tap {label}."
                txt = translate(en, k) if k != "en" else en
                p = os.path.join(CACHE, f"menu_{k}.wav")
                open(p, "wb").write(c.synthesize(txt, LANGS[k][4]).audio)
                paths.append(p)
        _to_ogg(paths, ogg)
        return ogg
    except Exception as e:
        last_error = f"menu: {e}"; print(last_error); return None


def tr(text, lang):
    """Translate English -> lang. Returns (text, ok). ok=False means we are showing English."""
    if lang == "en" or not text.strip(): return text, True
    if not available(): return text, False
    out = translate(text, lang)
    return out, (out != text)

def quota_hit(): return "quota" in last_error.lower()

def clip_for(lang, level):
    """Human-recorded clip (best quality, costs no API calls). voice_clips/{lang}_{LEVEL}.ogg"""
    for name in (f"{lang}_{level}.ogg", f"{lang}_{level}.mp3", f"{lang}_{level}.m4a"):
        pth = os.path.join(CLIPS, name)
        if os.path.exists(pth): return pth
    return None

def speak_english_fallback(text):
    """English-only fallback when Khaya is out of quota. Uses gTTS (needs internet, no key)."""
    global last_error
    try:
        from gtts import gTTS
        base = os.path.join(CACHE, "gtts_" + hashlib.md5(text.encode()).hexdigest())
        if not os.path.exists(base + ".ogg"):
            gTTS(text, lang="en", tld="com.gh").save(base + ".mp3")
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", base + ".mp3", "-c:a", "libopus", "-b:a", "32k", base + ".ogg"], check=True)
        return base + ".ogg"
    except Exception as e:
        last_error = (last_error + " | " if last_error else "") + f"gtts: {e}"; return None
