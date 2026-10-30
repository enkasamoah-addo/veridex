"""Optional LLM via any OpenAI-compatible endpoint. Works with free keys:
GROQ_API_KEY (api.groq.com) or GEMINI_API_KEY (Google AI Studio). Returns None if no key/failure
so every caller has a rule-based fallback."""
import os, json, httpx
def _cfg():
    if os.environ.get("GROQ_API_KEY"):
        return "https://api.groq.com/openai/v1", os.environ["GROQ_API_KEY"], os.environ.get("LLM_MODEL", "openai/gpt-oss-20b")
    if os.environ.get("GEMINI_API_KEY"):
        return "https://generativelanguage.googleapis.com/v1beta/openai", os.environ["GEMINI_API_KEY"], os.environ.get("LLM_MODEL", "gemini-2.5-flash")
    return None
def available(): return _cfg() is not None
def chat(messages, json_mode=False, temperature=0.8, timeout=25):
    cfg = _cfg()
    if not cfg: return None
    base, key, model = cfg
    body = {"model": model, "messages": messages, "temperature": temperature}
    if json_mode: body["response_format"] = {"type": "json_object"}
    try:
        r = httpx.post(f"{base}/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print("LLM error:", e); return None
