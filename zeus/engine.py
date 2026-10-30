"""Ananse engine: runs by itself on every flagged check.
  1. TRIAGE   - a citizen's flagged check becomes a case; Ananse inspects the websites, cross-checks numbers
                against earlier reports and writes a short brief for the SEC officer.
  2. ENGAGE   - Ananse (persona 'Kofi') opens the conversation and keeps the suspected scammer talking.
                Every scammer message is mined for payment numbers, names, links, licence claims.
  3. HAND-OFF - once payment details + a name or link are captured, the case is 'evidence_ready' on the SEC dashboard.
SAFETY: Ananse never sends money or real personal data. In this build the 'scammer' is a teammate or a scripted
simulator in the demo chat. Live engagement with real suspects needs written SEC authorisation."""
import os, sys, re, json, threading, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import db
from core import checker, llm, sitecheck, accountname
from core.idents import extract, merge, domain_of
from zeus.honeypot import PERSONA
from zeus.scammer_sim import SCRIPT

LIST_KEYS = ("momo_numbers", "bank_accounts", "banks", "links", "handles", "promised_returns", "licence_claimed", "account_names")
ACTIVE = ("ananse_waiting", "ananse_engaged", "evidence_ready")
now = lambda: datetime.datetime.now().isoformat(timespec="seconds")
empty = lambda: {k: [] for k in LIST_KEYS}

ASKS = [  # (key, still_missing?, [question variants])
    ("company", lambda e: True, ["Hello, I got your message. Which company is this please? I want to be sure."]),
    ("returns", lambda e: not e["promised_returns"], ["Okay. How much will I get back if I put in GHS 2,000, and when?",
                                                      "So if I invest GHS 2,000, exactly how much do I receive, and on what day?"]),
    ("licence", lambda e: not e["licence_claimed"], ["Is the company licensed by SEC? Please send me the licence number.",
                                                      "My brother says I must see the SEC licence number first. Can you send it?"]),
    ("link", lambda e: not e["links"], ["Please send me the website or link so I can see it myself.",
                                         "Do you have a website? I want to read about the company before I send anything."]),
    ("payment", lambda e: not (e["momo_numbers"] or e["bank_accounts"]), ["Alright I'm ready. Where do I send the money? Please send the number and the name on it.",
                                                                        "I have the money ready. Which number or account must I pay into?"]),
    ("bank", lambda e: bool(e["bank_accounts"]) and not e["banks"], ["Which bank is that account with please? I will use my banking app.",
                                                                    "Is that account at GCB, Absa or which bank? My app asks me to choose."]),
    ("name", lambda e: bool(e["momo_numbers"] or e["bank_accounts"]) and not e["account_names"],
     ["Ok. When I send it, what name will show on my MoMo screen? I want to be sure it's the right person.",
      "Please tell me the full name the account is registered in, so I don't send to the wrong person."]),
    ("people", lambda e: True, ["Who is the owner? My brother wants to join too, who should he talk to?"]),
]
REACT = [  # (regex on scammer's last message, key, reply)
    (r"\bfee\b|registration|activation|processing|tax first|unlock", "fee", "A fee first? Why must I pay before I get anything? Please explain how it works."),
    (r"hurry|today only|limited slots|last chance|expires", "rush", "Why is it so urgent? I am interested, I just need to be sure it is safe."),
    (r"refer|commission|bring (your )?friends", "refer", "Interesting. How much do I earn if my brother joins too?"),
]
WRAP = "Ok I am at the bank now, let me send it. Give me 10 minutes and I will send the screenshot. Thank you."

def _load(cid):
    c = db.get_case(cid)
    return c, json.loads(c["transcript"] or "[]"), json.loads(c["evidence"] or "{}")

def _done(ev, tr=()):
    """Evidence is complete when we hold a payment number AND the name on it (or Ananse has already pushed 6 times)."""
    pay = bool(ev.get("momo_numbers") or ev.get("bank_accounts"))
    return pay and (bool(ev.get("account_names")) or sum(1 for t in tr if t["role"] == "zeus") >= 6)

def _asked(tr, key): return sum(1 for t in tr if t.get("ask") == key)

def missing(ev):
    e = {k: ev.get(k, []) for k in LIST_KEYS}
    return [k for k, miss, _ in ASKS if k not in ("company", "people") and miss(e)]

def make_reply(tr, ev):
    """Ananse's next message: reacts to what was just said, then asks for whatever evidence is still missing."""
    e = {k: ev.get(k, []) for k in LIST_KEYS}
    last = next((t["text"] for t in reversed(tr) if t["role"] == "scammer"), "")
    if _done(ev, tr) and not any(t.get("ask") == "wrap" for t in tr): return WRAP, "wrap"
    if _done(ev, tr): return "Ok, I am coming. Please wait for me.", "wait"
    if llm.available():
        sysmsg = PERSONA + "\nEvidence still missing (work on the FIRST one next, naturally): " + (", ".join(missing(ev)) or "none") + \
                 ".\nAlready captured: " + ", ".join(k for k in LIST_KEYS if ev.get(k)) + "." + \
                 "\nYour earlier messages (do NOT repeat these questions): " + " | ".join(t["text"] for t in tr if t["role"] == "zeus")[-700:]
        msgs = [{"role": "system", "content": sysmsg}] + [{"role": "assistant" if t["role"] == "zeus" else "user", "content": t["text"]} for t in tr[-12:]]
        out = llm.chat(msgs, temperature=0.9)
        if out: return out.strip().strip('"'), (missing(ev) or ["chat"])[0]
    for rx, key, text in REACT:
        if re.search(rx, last, re.I) and _asked(tr, key) == 0: return text, key
    for key, miss, variants in ASKS:                       # first pass: never asked yet
        if miss(e) and _asked(tr, key) == 0: return variants[0], key
    for key, miss, variants in ASKS:                       # second pass: ask again, differently
        if miss(e) and 0 < _asked(tr, key) < len(variants): return variants[_asked(tr, key)], key
    return "Okay I understand. So what is the next step for me to start?", "next"

def opener(offer_text):
    if llm.available():
        out = llm.chat([{"role": "system", "content": PERSONA}, {"role": "user", "content": offer_text}], temperature=0.9)
        if out: return out.strip().strip('"')
    return "Hello, I saw your offer. Is it still open? I have some savings I want to invest, please tell me more."

# ---------- brief for the SEC officer ----------
def build_brief(c, ev, v, sites, related):
    pts = []
    a = checker.annualised(c["text"] + " " + " ".join(ev.get("promised_returns", [])))
    if a: pts.append(f"Promised return: {a[2]} (about {a[1]:,.0f}% a year).")
    if v.matched: pts.append(f"Name matches '{v.matched['name']}': {v.matched['detail']}.")
    cont = ev.get("handles", []) + ev.get("momo_numbers", [])
    if cont: pts.append("Contact points: " + ", ".join(cont) + ".")
    for s in sites:
        bits = [f"{s['domain']}"]
        if s["age_days"] is not None: bits.append(f"created {s['age_days']} days ago")
        if s["impersonates"]: bits.append(f"imitates {s['impersonates']}")
        if s["clone_of"]: bits.append(f"copies licensed firm '{s['clone_of']}'")
        if s["asks_payment"]: bits.append("asks for MoMo / ID / password")
        if s["handles"] or s["phones"]: bits.append("contacts on page: " + ", ".join(s["handles"] + s["phones"]))
        if not s["fetched"]: bits.append("page could not be opened")
        pts.append("Website: " + "; ".join(bits) + ".")
    for a in ev.get("account_lookups", []):
        who = a["verified_name"] or (ev["account_names"][0] if ev.get("account_names") else "") or "name not yet obtained"
        line = f"Payment account: {a['id']}" + (f" ({a['network']})" if a["network"] else "") + (f" at {a['bank']}" if a["bank"] else "") + f", name: {who}"
        if a["verified_name"]: line += f" (verified: {a['verified_by']})"
        if a["known_names"]: line += f". Earlier reports named this account holder: {', '.join(a['known_names'])}"
        pts.append(line + ".")
    if related: pts.append(f"The same number/link/handle appears in {len(related)} other report(s) (cases {', '.join('#' + str(r) for r in related[:6])}).")
    if ev.get("licence_claimed"): pts.append("Claims licence: " + ", ".join(ev["licence_claimed"]) + " (not verified).")
    st = c["status"]
    nxt = {"ananse_waiting": "Ananse has opened the chat and is waiting for the suspect to reply.",
           "ananse_engaged": "Ananse is in conversation and still collecting payment details.",
           "evidence_ready": "Evidence is complete. Officer decision needed: warning, MoMo flag, or referral."}.get(st, "Ananse is preparing.")
    head = {"RED": "High risk.", "YELLOW": "Unclear."}.get(v.level, "Looks licensed.") + " " + (v.reasons[0] if v.reasons else "")
    return {"summary": head, "points": pts, "next": nxt}

def refresh(cid):
    """Re-inspect sites, re-score and rewrite the brief. Safe to call repeatedly (runs in background)."""
    try:
        c, tr, ev = _load(cid)
        text = " ".join(t["text"] for t in tr if t["role"] == "scammer") or c["text"]
        links = [u for u in ev.get("links", []) if not sitecheck.skip(domain_of(u))][:3]
        sites = [sitecheck.investigate(u) for u in links]
        v = checker.check(text, exclude_case=cid)
        related = db.find_related([i for i in ev.get("momo_numbers", []) + ev.get("handles", []) + [domain_of(u) for u in links] if i], cid)
        with db.LOCK:
            c, tr, ev = _load(cid)
            if ev.get("momo_numbers") and v.level != "RED":
                v.level = "RED"; v.reasons.insert(0, "They asked for payment to a personal mobile money number (captured in chat).")
            if related and v.level != "RED" and False: pass
            lk = [accountname.lookup(n, "momo", exclude_id=cid) for n in ev.get("momo_numbers", [])] + \
                 [accountname.lookup(n, "bank", bank=(ev.get("banks") or [None])[0], exclude_id=cid) for n in ev.get("bank_accounts", [])]
            ev["account_lookups"] = lk
            ev["site_reports"] = sites
            ev["site_contacts"] = sorted({p for s in sites for p in s["phones"]} | {h for s in sites for h in s["handles"]})
            ev["related_cases"] = related
            ev["brief"] = build_brief(c, ev, v, sites, related)
            ent = c["entity"] or (v.matched or {}).get("name", "") or (sites[0]["title"][:60] if sites and sites[0]["title"] else "") or (links and domain_of(links[0])) or ""
            db.update(cid, evidence=ev, level=v.level, reasons=json.dumps(v.reasons), flags=json.dumps(v.flags), entity=ent)
    except Exception as e:
        print("Ananse refresh error:", e)

def triage(cid):
    if not db.claim(cid, ("new", "reported_by_user"), "ananse_triaging"): return
    try:
        c = db.get_case(cid)
        ev = merge(empty(), extract(c["text"]))
        tr = [{"role": "scammer", "text": c["text"], "t": now(), "note": "Offer as received by the citizen"}]
        tr.append({"role": "zeus", "text": opener(c["text"]), "t": now()})
        with db.LOCK:
            old = json.loads(db.get_case(cid)["evidence"] or "{}"); old.update(ev)
            db.update(cid, evidence=old, transcript=tr, status="ananse_waiting")
        refresh(cid)
    except Exception as e:
        print("Ananse triage error:", e); db.update(cid, status="ananse_failed")

def on_scammer_message(cid, text):
    text = text.strip()
    if not text: return db.get_case(cid)
    with db.LOCK:
        c, tr, ev = _load(cid)
        if c["status"] not in ACTIVE: raise ValueError("Ananse is not in a conversation on this case")
        tr.append({"role": "scammer", "text": text, "t": now()})
        ev.update(merge(ev, extract(text)))
        db.update(cid, transcript=tr, evidence=ev)
    reply, key = make_reply(tr, ev)                 # may call the LLM: done outside the lock
    with db.LOCK:
        c, tr2, ev2 = _load(cid)
        tr2.append({"role": "zeus", "text": reply, "t": now(), "ask": key})
        status = "evidence_ready" if _done(ev2, tr2) else "ananse_engaged"
        db.update(cid, transcript=tr2, status=status)
    threading.Thread(target=refresh, args=(cid,), daemon=True).start()
    return db.get_case(cid)

def sim_scammer_line(cid):
    c, tr, ev = _load(cid)
    k = sum(1 for t in tr if t["role"] == "scammer") - 1      # first one is the citizen's forwarded offer
    return SCRIPT[min(1 + k, len(SCRIPT) - 1)]

def worker(stop):
    """Background loop: picks up every newly flagged case and works it, no button needed."""
    while not stop.is_set():
        try:
            for c in db.pending_for_ananse(): triage(c["id"])
        except Exception as e:
            print("Ananse worker error:", e)
        stop.wait(3)
