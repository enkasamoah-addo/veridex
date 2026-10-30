"""'Truecaller for payment accounts': who does this number / account belong to?
Sources, in order of strength:
  1. BANK RECORD (optional): Paystack 'resolve account' returns the registered holder of a Ghana BANK account.
     Needs a Paystack business key in PAYSTACK_SECRET_KEY. Free endpoint, but only for personal bank accounts.
  2. VERIDEX MEMORY: names Ananse or users already captured for the same number in earlier cases.
  3. NETWORK: which mobile money network a number belongs to (from the number prefix).
MoMo holder names are only visible inside the telco/MoMo app before you confirm a payment. A direct name
lookup for MoMo needs a telco or GhIPSS partnership; that is on our roadmap, not in this build."""
import os, json, re, time
import httpx
from rapidfuzz import fuzz, process
import db
from core.idents import network_of

_BANKS = {"t": 0, "list": []}

def _paystack_banks(key):
    if time.time() - _BANKS["t"] < 3600 and _BANKS["list"]: return _BANKS["list"]
    r = httpx.get("https://api.paystack.co/bank", params={"country": "ghana", "perPage": 100}, headers={"Authorization": f"Bearer {key}"}, timeout=8)
    _BANKS["list"] = r.json().get("data", []); _BANKS["t"] = time.time(); return _BANKS["list"]

def bank_holder(account, bank_name):
    key = os.environ.get("PAYSTACK_SECRET_KEY")
    if not key or not bank_name: return None
    try:
        banks = _paystack_banks(key)
        best = process.extractOne(bank_name, [b["name"] for b in banks], scorer=fuzz.WRatio)
        if not best or best[1] < 70: return None
        code = banks[best[2]]["code"]
        r = httpx.get("https://api.paystack.co/bank/resolve", params={"account_number": account, "bank_code": code}, headers={"Authorization": f"Bearer {key}"}, timeout=8)
        if r.status_code == 200 and r.json().get("status"): return r.json()["data"]["account_name"]
    except Exception as e:
        print("Paystack lookup error:", e)
    return None

def memory_names(identifier, exclude_id=None):
    """Names already captured in other cases that contain this number/account."""
    names, cases = {}, []
    for c in db.all_cases():
        if c["id"] == exclude_id: continue
        ev = json.loads(c["evidence"] or "{}")
        ids = set(ev.get("momo_numbers", []) + ev.get("bank_accounts", []))
        if identifier in ids or identifier in re.sub(r"(?<=\d)[ -](?=\d)", "", c["text"] or ""):
            cases.append(c["id"])
            if len(ids) == 1:                       # only attribute a name when the case has a single account
                for n in ev.get("account_names", []): names[n] = names.get(n, 0) + 1
    return sorted(names), cases

def lookup(identifier, kind, bank=None, exclude_id=None):
    names, cases = memory_names(identifier, exclude_id)
    out = {"id": identifier, "kind": kind, "network": network_of(identifier) if kind == "momo" else "", "bank": bank or "",
           "verified_name": "", "verified_by": "", "known_names": names, "seen_in": cases}
    if kind == "bank":
        n = bank_holder(identifier, bank)
        if n: out["verified_name"], out["verified_by"] = n, "Bank record via Paystack"
    return out
