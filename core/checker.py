"""Core checker: real SEC/NPRA data + plain-language, explained verdicts.
Every reason is rule-based and traceable to a source (no LLM guessing on safety)."""
import csv, os, re, datetime
from dataclasses import dataclass, field
from rapidfuzz import fuzz, process

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
NOISE = re.compile(r"\b(limited|ltd|plc|company|co|ghana|gh|the|and|of|ventures?|group|platform|asset|assets|management|managers?|capital|investments?|investment|securities|financial|services?|service|fund|funds|advisors?|advisory|holdings?|partners|trust|pensions?|bank|cap|wealth|fintech|exchange|trading|trade|invest)\b|[^a-z0-9 ]")

def norm(s):
    s = NOISE.sub(" ", s.lower())
    return re.sub(r"\s+", " ", s).strip()

def _rows(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))

def _expand(name):
    """'QX Broker/Qumatix' or 'Heritage (formerly Futurepip)' -> several aliases."""
    out = {name}
    for part in re.split(r"/|\((?:formerly|Formerly)?|\)", name):
        part = part.strip(" ()")
        if len(part) > 2:
            out.add(part)
    return out

REGISTRY = []  # (alias_norm, display, list_type, detail, source)
def _load():
    for r in _rows("sec_unlicensed_entities_warnings.csv"):
        for a in _expand(r["entity"]):
            REGISTRY.append((norm(a), a.strip(), "UNLICENSED",
                f"was named by the SEC as operating without a licence (notice dated {r['notice_date']})", r["source_url"]))
    for r in _rows("sec_revoked_fund_managers_2019.csv"):
        for a in _expand(r["name"]):
            REGISTRY.append((norm(a), a.strip(), "REVOKED",
                "had its SEC licence revoked in the SEC notice of 8 Nov 2019", r["source_url"]))
    for fn, label in (("npra_pension_fund_managers.csv", "pension fund manager"),
                      ("npra_corporate_trustees.csv", "pension trustee"),
                      ("npra_pension_fund_custodians.csv", "pension fund custodian")):
        for r in _rows(fn):
            REGISTRY.append((norm(r["name"]), r["name"], "LICENSED",
                f"is on the National Pensions Regulatory Authority's list of {label}s (licence {r['licence_no']}, valid until {r['licence_valid_until']})",
                r["source_url"]))
    for r in _rows("sec_licensed_2026q1.csv"):
        REGISTRY.append((norm(r["name"]), r["name"], "LICENSED",
            f"was licensed by the SEC in the first quarter of 2026 ({r['category']})", r["source_url"]))
    for r in _rows("sec_licensed_2026q1.csv"):
        REGISTRY.append((norm(r["name"]), r["name"], "LICENSED",
            f"was licensed by the SEC in the first quarter of 2026 ({r['category']})", r["source_url"]))
    for r in _rows("sec_fund_managers_remaining_after_2019_revocation.csv"):
        t = "FLAGGED2019" if r["flagged_by_sec_for_major_issues_2019"] == "yes" else "LISTED2019"
        d = ("kept its licence in Nov 2019 but the SEC flagged it for major regulatory issues" if t == "FLAGGED2019"
             else "kept its SEC licence in Nov 2019 (older list; current status not confirmed)")
        REGISTRY.append((norm(r["name"]), r["name"], t, d, r["source_url"]))
_load()
BENCH = {r["instrument"]: (float(r["interest_rate_pct_pa"]), r["auction_date"]) for r in _rows("benchmark_rates.csv")}
KNOWN_DOMAINS = {r["domain"].lower() for r in _rows("known_bad_domains.csv")}
REGISTRY = [r for r in REGISTRY if len(r[0]) >= 2]
KEYS = [r[0] for r in REGISTRY]
SHORT = {}
for _i, _r in enumerate(REGISTRY):
    if len(_r[0]) < 4:
        SHORT.setdefault(_r[0], _i)

# --- red-flag rules: (id, regex, strong?, plain reason) ---
FLAGS = [
 ("guaranteed", r"guarantee|risk[- ]?free|100% safe|no risk|sure profit|cannot lose", True,
  "They promise guaranteed or risk-free profit. Real investments always carry risk, and no licensed company is allowed to promise this."),
 ("double", r"doubl\w+ (your )?(money|investment)|triple|10x|\bdouble\b.*\b(days?|week)", True,
  "They say your money will double or triple. This is the most common sign of a Ponzi (pyramid) scheme."),
 ("quick", r"quick money|fast money|get rich|easy money|passive income|earn \w+ daily|make money (fast|daily)", False,
  "They sell 'quick easy money'. Real wealth building takes time, and scams always sell speed."),
 ("urgent", r"today only|limited (slots|spots|time|offer)|hurry|last chance|expires|within \d+ (hours|minutes)|act now|only \d+ (slots|spots)", False,
  "They are rushing you ('limited slots', 'today only'). Scammers create pressure so you do not stop to check."),
 ("momo", r"momo|mobile money|send (the )?(money|funds|payment) to|0[235][0-9]{8}", False,
  "They want you to pay into a personal mobile money or phone number. A licensed company collects money through a bank account in the company's name."),
 ("fee", r"(withdrawal|registration|activation|release|processing|tax|clearance) fee", True,
  "They ask for a fee before you can get your money out. This is a classic trick: you pay, then they ask for more."),
 ("referral", r"refer(ral)?|invite (your )?friends|recruit|downline|team bonus|commission for (each|every)", False,
  "Your earnings depend on bringing in other people. That is how pyramid schemes work."),
 ("crypto", r"crypto|bitcoin|usdt|forex|trading bot|ai trading|binary|nft|mining", False,
  "It involves crypto, forex or a 'trading bot'. Since 2025 these must be licensed in Ghana, and most social-media offers are not."),
 ("social", r"whatsapp|telegram|dm me|inbox|facebook|tiktok|instagram|joined? (our )?(group|channel)", False,
  "It reached you through WhatsApp, Telegram or social media. Licensed firms do not recruit investors through random messages."),
 ("endorse", r"(president|mahama|akufo|celebrity|minister|bank of ghana).{0,30}(endors|invest|recommend)", True,
  "It claims a famous person or the government backs it. Fake endorsement videos are being used by scammers."),
]

@dataclass
class Verdict:
    level: str            # RED | YELLOW | GREEN
    headline: str
    reasons: list = field(default_factory=list)
    do_now: list = field(default_factory=list)
    comfort: str = ""
    matched: dict = None
    flags: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    checks: list = field(default_factory=list)   # [(icon, label)]

def _expired(detail):
    m = re.search(r"valid until (\d{4}-\d{2}-\d{2})", detail or "")
    return bool(m) and datetime.date.fromisoformat(m.group(1)) < datetime.date.today()

SEC_LINE = "Call the SEC toll-free on 0800 100 065 (or 0302 768 970-2) and ask: 'Is this company licensed?'"

def match_entity(text, threshold=88):
    """Find the best registry match for any company name inside the message."""
    t = norm(text)
    if not t:
        return None
    best = None
    # whole-text vs name, and sliding word windows so names inside long messages are found
    words = t.split()
    cands = {t}
    for n in (1, 2, 3, 4):
        for i in range(len(words) - n + 1):
            cands.add(" ".join(words[i:i + n]))
    for c in cands:
        if len(c) < 4:
            if c in SHORT and c in words:
                best = (c, 100, SHORT[c])
            continue
        m = process.extractOne(c, KEYS, scorer=fuzz.ratio, score_cutoff=threshold)
        if m and (best is None or m[1] > best[1]):
            best = (m[0], m[1], m[2])
    if not best:
        return None
    r = REGISTRY[best[2]]
    # prefer the most dangerous list if the same name appears more than once
    sev = {"UNLICENSED": 0, "REVOKED": 1, "FLAGGED2019": 2, "LICENSED": 3, "LISTED2019": 4}
    same = [x for x in REGISTRY if x[0] == r[0]]
    r = sorted(same, key=lambda x: sev[x[2]])[0]
    return {"name": r[1], "type": r[2], "detail": r[3], "source": r[4], "score": best[1]}

RET = re.compile(r"(\d+(?:\.\d+)?)\s?%\s*(?:returns?\s*|profit\s*|interest\s*|roi\s*|bonus\s*)?(?:(daily|per day|a day|every day|weekly|per week|a week|every week|monthly|per month|a month|every month|yearly|annually|per year|a year)|(?:in|within|after|every)\s+(\d+)\s*(days?|weeks?|months?))", re.I)
AMT = re.compile(r"(?:GH[SC₵]?\s?|₵)\s?(\d[\d,]*(?:\.\d+)?)[^\d%]{1,40}?(?:GH[SC₵]?\s?|₵)?\s?(\d[\d,]*(?:\.\d+)?)[^\d%]{0,20}?(?:in|within|after)\s+(\d+)\s*(days?|weeks?|months?)", re.I)
PER_YEAR = {"day": 365, "week": 52, "month": 12, "year": 1}
def annualised(text):
    """Largest promised return, converted to % per year. Returns (pct, per_year_pct, label) or None."""
    best = None
    for m in RET.finditer(text):
        pct = float(m.group(1))
        if m.group(2):
            unit = next(u for u in PER_YEAR if u in m.group(2).lower().replace("annually", "year").replace("yearly", "year")); n = 1
        else:
            n = int(m.group(3)); unit = m.group(4).lower().rstrip("s")
        yr = pct * PER_YEAR[unit] / n
        if not best or yr > best[1]: best = (pct, yr, f"{pct:g}% every {n if n>1 else ''} {unit}{'s' if n>1 else ''}".replace("  ", " "))
    # "GHS 2000 ... 2400 in 7 days": work out the gain from the two amounts
    for m in AMT.finditer(text):
        a, b = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
        if a > 0 and b > a:
            n = int(m.group(3)); unit = m.group(4).lower().rstrip("s")
            pct = (b - a) / a * 100; yr = pct * PER_YEAR[unit] / n
            if not best or yr > best[1]: best = (pct, yr, f"{pct:g}% in {n} {unit}{'s' if n>1 else ''}")
    return best

_RDAP = {}
def domain_age_days(domain):
    """Public RDAP lookup (no key). Returns age in days or None if it could not be checked."""
    if domain in _RDAP: return _RDAP[domain]
    age = None
    try:
        import httpx
        r = httpx.get(f"https://rdap.org/domain/{domain}", timeout=4, follow_redirects=True)
        if r.status_code == 200:
            for e in r.json().get("events", []):
                if e.get("eventAction") == "registration":
                    d = datetime.date.fromisoformat(e["eventDate"][:10]); age = (datetime.date.today() - d).days
    except Exception:
        pass
    _RDAP[domain] = age; return age

def dynamic_flags(text, exclude_case=None):
    """Extra, data-backed signals: unrealistic returns, new/known-bad websites, numbers already reported."""
    from core.idents import extract, domain_of
    out, info = [], {"returns": None, "site_age": None, "known": 0}
    a = annualised(text)
    if a and a[1] > 40:
        t = BENCH.get("364-day T-bill")
        ref = f" The Government of Ghana pays about {t[0]:.1f}% a year on 1-year Treasury bills (BoG auction, {t[1]})." if t else ""
        out.append(("returns", True, f"They promise {a[2]}. That is about {a[1]:,.0f}% a year, and no real investment can safely pay that.{ref}"))
        info["returns"] = a
    ids = extract(text)
    import db
    kb = db.known_bad(exclude_case)
    hits = [i for i in ids["momo_numbers"] + ids["bank_accounts"] if i in kb] + [h for h in ids["handles"] if h.lower() in kb]
    for u in ids["links"]:
        d = domain_of(u)
        if d in KNOWN_DOMAINS or d in kb: hits.append(d)
    if hits:
        info["known"] = len(hits)
        out.append(("known", True, "A phone number, account, link or handle in this offer has already been reported as a scam in our records or in published warnings."))
    from core import sitecheck
    from concurrent.futures import ThreadPoolExecutor
    todo = [u for u in ids["links"] if not sitecheck.skip(domain_of(u))][:2]
    info["sites"] = []
    if todo:
        with ThreadPoolExecutor(max_workers=2) as ex:
            reports = list(ex.map(sitecheck.investigate, todo))
        info["sites"] = reports
        for r in reports:
            d, age = r["domain"], r["age_days"]
            if age is not None: info["site_age"] = age if info["site_age"] is None else min(info["site_age"], age)
            if r["impersonates"]:
                out.append(("lookalike", True, f"Their website address ({d}) imitates {r['impersonates']}. Scammers copy trusted names and spell them almost the same."))
            if r["clone_of"]:
                out.append(("clone", age is not None and age < 365, f"Their website uses the name of the licensed company '{r['clone_of']}', but the web address ({d}) is not theirs. This is how scammers copy real firms."))
            if r["asks_payment"]:
                out.append(("sitepay", True, f"Their website ({d}) asks you to pay by mobile money, or to hand over ID details, a PIN/OTP or a password."))
            if age is not None and age < 90: out.append(("newsite", True, f"Their website ({d}) was created only {age} days ago. Real investment firms have older websites."))
            elif age is not None and age < 365: out.append(("newsite", False, f"Their website ({d}) is less than a year old ({age} days)."))
    return out, info

def detect_flags(text):
    found = []
    text = text + " " + re.sub(r"(?<=\d)[ -](?=\d)", "", text)   # catch phone numbers written with spaces
    for fid, rx, strong, why in FLAGS:
        if re.search(rx, text, re.I):
            found.append((fid, strong, why))
    return found

COMFORT = {
 "RED": "You did the right thing by checking first. These schemes are built to catch honest people who want a better life, so please do not feel foolish for being tempted. Your money is safe as long as you have not paid.",
 "YELLOW": "Checking first is the smartest thing you can do. Not being sure is okay. Take a day, ask the SEC, and let the real facts decide, not the pressure.",
 "GREEN": "Good news, and good on you for checking. Still, scammers sometimes copy real company names, so confirm using the official numbers below before you pay.",
}

def check(text: str, exclude_case=None) -> Verdict:
    m = match_entity(text)
    flags = detect_flags(text)
    dyn, info = dynamic_flags(text, exclude_case)
    flags = flags + dyn
    strong = [f for f in flags if f[1]]
    reasons, sources, do = [], [], []
    if m:
        sources.append(m["source"])

    if info["known"]:
        lvl = "RED"
        reasons.append("Something in this offer (a number, account, link or handle) has already been reported as a scam.")
    elif m and m["type"] in ("UNLICENSED", "REVOKED"):
        lvl = "RED"
        sim = "" if m["score"] >= 96 else "The name looks very similar to "
        reasons.append(f"{sim}'{m['name']}', which {m['detail']}.")
    elif (len(strong) >= 1 and len(flags) >= 2) or len(strong) >= 2:
        lvl = "RED"
        if m and m["type"] == "LICENSED":
            reasons.append(f"The name matches the licensed firm '{m['name']}', but this offer has several scam warning signs. Real licensed firms do not make offers like this, so someone may be copying their name.")
        else:
            reasons.append("We could not find this company on any list of licensed firms we hold, and the offer has several warning signs.")
    elif m and m["type"] == "LICENSED" and not flags and _expired(m["detail"]):
        lvl = "YELLOW"
        reasons.append(f"'{m['name']}' {m['detail']}.")
        reasons.append("That is the most recent official list we hold, and that licence period has ended. It is very likely renewed, but please confirm with the SEC before paying.")
    elif m and m["type"] == "LICENSED" and not flags:
        lvl = "GREEN"
        reasons.append(f"'{m['name']}' {m['detail']}.")
        reasons.append("We found no scam warning signs in what you sent.")
    elif m and m["type"] == "LICENSED":
        lvl = "YELLOW"
        reasons.append(f"The company name matches '{m['name']}', which {m['detail']}.")
        reasons.append("But the offer you received has warning signs, and scammers often copy real company names. Make sure it is really them.")
    elif m and m["type"] == "FLAGGED2019":
        lvl = "YELLOW"
        reasons.append(f"'{m['name']}' {m['detail']}.")
    elif m and m["type"] == "LISTED2019":
        lvl = "YELLOW"
        reasons.append(f"'{m['name']}' {m['detail']}. We cannot confirm it is still licensed today.")
    else:
        lvl = "YELLOW"
        reasons.append("We could not find this name on the SEC or pension-regulator lists we hold. That does not prove it is fake, but it means we cannot say it is safe.")
    for fid, strong_, why in flags:
        if fid == "known": continue
        reasons.append(why)

    if lvl == "RED":
        head = "🔴 DANGER: this looks like a scam. Please do not send any money."
        do = ["Do not send money, MoMo, or personal details (Ghana Card, PIN, OTP).",
              "Do not forward it to friends or family; warn them instead.",
              SEC_LINE,
              "If you already paid: call your MoMo provider/bank immediately (the first hours matter most) and report to the Cyber Security Authority on 292."]
    elif lvl == "YELLOW":
        head = "🟡 NOT SURE: please do not pay yet."
        do = ["Wait. Do not pay today, whatever deadline they gave you.",
              SEC_LINE,
              "Ask them for their SEC licence number, then confirm it with the SEC yourself.",
              "Never pay into a personal MoMo number."]
    else:
        head = "🟢 LOOKS LICENSED: the company is on an official list."
        do = ["Confirm with the SEC on 0800 100 065 that the licence is current.",
              "Pay only into an account in the company's own name, never a personal number.",
              "Keep every receipt and contract."]
    if any(f[0] in ("momo", "fee") for f in flags):
        do.insert(1, "Before you ever send MoMo, check the registered name that appears on your screen. If it is a person's name and not the company's, stop.")
    fl = {f[0] for f in flags}
    t = (m or {}).get("type")
    reg = "❌" if t in ("UNLICENSED", "REVOKED") else "⚠️" if t in ("FLAGGED2019", "LISTED2019") or (t == "LICENSED" and (_expired(m["detail"]) or flags)) else "✅" if t == "LICENSED" else "❔"
    ret = "❌" if "returns" in fl else ("✅" if info["returns"] is None and annualised(text) else "➖")
    pay = "❌" if fl & {"momo", "fee"} else "➖"
    sites = info.get("sites", [])
    sev = [f["sev"] for r_ in sites for f in r_["findings"]]
    site = "➖" if not sites else "❌" if ("bad" in sev) else "⚠️" if ("warn" in sev) else "✅" if any(r_["age_days"] is not None for r_ in sites) else "➖"
    rep = "❌" if (info["known"] or t in ("UNLICENSED", "REVOKED")) else "✅"
    pres = "⚠️" if fl & {"urgent", "referral", "social", "quick", "endorse", "double", "guaranteed"} else "✅"
    checks = [(reg, "Is it on an official licence list?"), (ret, "Are the promised returns realistic?"), (pay, "Is the payment method safe?"),
              (site, "Does the website look genuine?"), (rep, "Has it been reported as a scam?"), (pres, "Free of pressure and recruiting tricks?")]
    return Verdict(lvl, head, reasons, do, COMFORT[lvl], m,
                   [f[0] for f in flags], list(dict.fromkeys(sources)), checks)

def spoken(v: Verdict) -> str:
    """Short, name-free summary for voice. Same text for same situation, so audio is cached and reused."""
    head = {"RED": "Danger. This looks like a scam. Do not send any money.",
            "YELLOW": "Not sure. Please do not pay yet.",
            "GREEN": "This company is on an official list."}[v.level]
    t = (v.matched or {}).get("type")
    if t == "UNLICENSED": why = "The SEC has named this company as unlicensed."
    elif t == "REVOKED": why = "The SEC took away this company's licence."
    elif t == "FLAGGED2019": why = "The SEC raised serious concerns about this company."
    elif t in ("LICENSED", "LISTED2019") and v.level == "GREEN": why = "We found no warning signs."
    elif t in ("LICENSED", "LISTED2019"): why = "This company is on an old official list, so please confirm it is still licensed."
    elif v.flags: why = "The offer has warning signs, like promised profit or pressure to pay quickly."
    else: why = "We could not find this company on the lists we hold."
    act = {"RED": "Call the SEC on 0800 100 065 to report it.",
           "YELLOW": "Call the SEC on 0800 100 065 and ask if they are licensed.",
           "GREEN": "Still confirm with the SEC on 0800 100 065 before you pay."}[v.level]
    return f"{head} {why} {act}"

def render(v: Verdict) -> str:
    out = [v.headline, ""]
    if v.checks:
        out += ["Our 6 checks:"] + [f"{i} {l}" for i, l in v.checks] + [""]
    out += ["Why:"]
    out += [f"• {r}" for r in v.reasons[:5]]
    out += ["", "What to do now:"] + [f"{i}. {d}" for i, d in enumerate(v.do_now, 1)]
    out += ["", v.comfort]
    return "\n".join(out)

if __name__ == "__main__":
    import sys
    print(render(check(" ".join(sys.argv[1:]))))
