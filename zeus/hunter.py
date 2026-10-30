"""Ananse hunter: finds leads, engages them (SIMULATION MODE), extracts evidence, hands a case to the SEC officer.
Lead sources: (1) citizen reports from the bot, (2) the SEC's own published warning lists.
SAFETY: in this build Ananse only talks to a simulated scammer. Live engagement needs SEC authorisation."""
import os, sys, csv, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import db
from core import checker
from zeus.honeypot import Session
from zeus.scammer_sim import SCRIPT

def seed_watchlist():
    """Load the SEC's published unlicensed-entity warnings as hunting leads (idempotent)."""
    have = {c["entity"] for c in db.all_cases() if c["source"] == "sec_watchlist"}
    n = 0
    path = os.path.join(os.path.dirname(__file__), "..", "data", "sec_unlicensed_entities_warnings.csv")
    for r in csv.DictReader(open(path, encoding="utf-8")):
        name = r["entity"]
        if name in have: continue
        v = checker.check(name)
        v.matched = v.matched or {"name": name}
        cid = db.add_case("sec_watchlist", "sec_notice", r["notice_ref"], f"{name}: named by the SEC as operating without a licence ({r['notice_date']}).", v)
        db.update(cid, status="lead", entity=name); n += 1
    return n

def engage(case_id, turns=None):
    """Run Ananse on a case. Opening message = the reported scam text (or a standard opener). Returns the case."""
    c = db.get_case(case_id)
    if not c: raise KeyError(case_id)
    opener = SCRIPT[0]
    if c["source"] in ("telegram_user", "user_report") and len(c["text"]) > 40: opener = c["text"]
    s = Session(opener, channel="simulation", source="ananse", user_ref=c["user_ref"])
    for m in (SCRIPT[1:turns] if turns else SCRIPT[1:]):
        s.reply(); s.hear(m)
    full = " ".join(t["text"] for t in s.transcript if t["role"] == "scammer")
    v = checker.check(full + " " + (c["entity"] or ""))
    if s.evidence["momo_numbers"] and v.level != "RED": v.level = "RED"
    db.update(case_id, evidence=s.evidence, transcript=s.transcript, status="ananse_engaged", level=v.level,
              reasons=json.dumps(v.reasons), flags=json.dumps(v.flags))
    return db.get_case(case_id)
