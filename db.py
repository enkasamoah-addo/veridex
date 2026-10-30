import re
import sqlite3, json, os, datetime
PATH = os.environ.get("VERIDEX_DB", os.path.join(os.path.dirname(__file__), "veridex.db"))
def conn():
    c = sqlite3.connect(PATH); c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS cases(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, source TEXT,
      channel TEXT, user_ref TEXT, text TEXT, level TEXT, entity TEXT, flags TEXT, reasons TEXT,
      status TEXT DEFAULT 'new', evidence TEXT DEFAULT '{}', transcript TEXT DEFAULT '[]', action TEXT DEFAULT '');
    """)
    return c
def add_case(source, channel, user_ref, text, v, evidence=None, transcript=None):
    c = conn()
    cur = c.execute("INSERT INTO cases(created,source,channel,user_ref,text,level,entity,flags,reasons,evidence,transcript) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (datetime.datetime.now().isoformat(timespec="seconds"), source, channel, user_ref, text, v.level,
         (v.matched or {}).get("name", ""), json.dumps(v.flags), json.dumps(v.reasons),
         json.dumps(evidence or {}), json.dumps(transcript or [])))
    c.commit(); return cur.lastrowid
def update(case_id, **kw):
    c = conn()
    for k, val in kw.items():
        if k in ("evidence", "transcript"): val = json.dumps(val)
        c.execute(f"UPDATE cases SET {k}=? WHERE id=?", (val, case_id))
    c.commit()
def all_cases():
    return [dict(r) for r in conn().execute("SELECT * FROM cases ORDER BY id DESC")]

def known_bad(exclude_id=None):
    """Identifiers (phones, domains, handles) seen in past HIGH-RISK cases -> number of cases."""
    import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from core.idents import extract, domain_of
    out = {}
    for r in conn().execute("SELECT text, evidence FROM cases WHERE level='RED' AND id != ?", (exclude_id or -1,)):
        ev = json.loads(r["evidence"] or "{}"); ex = extract(r["text"] or "")
        ids = set(ev.get("momo_numbers", []) + ex["momo_numbers"] + ev.get("bank_accounts", []) + ex["bank_accounts"]
                  + [h.lower() for h in ev.get("handles", []) + ex["handles"]]
                  + [domain_of(u) for u in ev.get("links", []) + ex["links"]])
        for i in ids: out[i] = out.get(i, 0) + 1
    return out

def get_case(case_id):
    r = conn().execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    return dict(r) if r else None

def stats():
    cs = all_cases()
    by = lambda k: sum(1 for c in cs if k(c))
    return {"cases": len(cs), "high_risk": by(lambda c: c["level"] == "RED"), "not_sure": by(lambda c: c["level"] == "YELLOW"),
            "licensed": by(lambda c: c["level"] == "GREEN"), "ananse_cases": by(lambda c: c["status"] in ("ananse_waiting", "ananse_engaged", "evidence_ready")),
            "awaiting_review": by(lambda c: c["status"] in ("evidence_ready", "ananse_engaged", "ananse_waiting", "reported_by_user")),
            "evidence_ready": by(lambda c: c["status"] == "evidence_ready"),
            "identifiers_flagged": len(known_bad())}

import threading
LOCK = threading.RLock()

def claim(case_id, from_statuses, to_status):
    """Atomically move a case to a new status. True if this caller won the claim (prevents double work)."""
    with LOCK:
        c = conn()
        q = ",".join("?" * len(from_statuses))
        cur = c.execute(f"UPDATE cases SET status=? WHERE id=? AND status IN ({q})", (to_status, case_id, *from_statuses))
        c.commit(); return cur.rowcount == 1

def pending_for_ananse():
    """Flagged citizen cases that Ananse has not picked up yet."""
    out = []
    for r in conn().execute("SELECT * FROM cases WHERE status IN ('new','reported_by_user') AND source IN ('telegram_user','web_user') ORDER BY id"):
        r = dict(r); fl = json.loads(r["flags"] or "[]")
        if r["level"] == "RED" or (r["level"] == "YELLOW" and fl): out.append(r)
    return out

def find_related(identifiers, exclude_id):
    """Other cases mentioning the same phone / link / handle."""
    n = set()
    for r in conn().execute("SELECT id, text, evidence FROM cases WHERE id != ?", (exclude_id,)):
        blob = (r["text"] or "") + (r["evidence"] or "")
        blob_d = re.sub(r"(?<=\d)[ -](?=\d)", "", blob) if False else blob
        if any(i and i.lower() in blob_d.lower() for i in identifiers): n.add(r["id"])
    return sorted(n)
