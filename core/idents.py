"""Pull payment/contact identifiers (phones, links, handles, accounts...) out of free text."""
import re
PHONE = re.compile(r"(?<!\d)(?:\+?233|0)[235]\d{8}(?!\d)")
URL = re.compile(r"(?:https?://|www\.|t\.me/)[^\s,;]+|\b[a-z0-9-]+\.(?:com|io|net|org|app|xyz|gh|club|site|online|top|vip|co)\b[^\s,;]*", re.I)
ACCT = re.compile(r"\b\d{10,16}\b")
HANDLE = re.compile(r"(?<!\w)@[A-Za-z0-9_]{4,}")
PCT = re.compile(r"\b\d{1,4}\s?%[^.,;\n]{0,25}")
LICENCE = re.compile(r"(?:licen[cs]e|reg(?:istration)?)[^\n]{0,15}?(?:no\.?|number|#)?\s*[:\-]?\s*([A-Z]{2,5}[/\-]?\d{3,}[A-Z0-9/\-]*)", re.I)
NAMEON = re.compile(r"(?:name|registered (?:to|as)|account name)\s*(?:is|:|-)?\s*([A-Z][a-z]+(?: [A-Z][a-z]+){1,3})")
BANKS = [("GCB Bank", r"\bgcb\b"), ("Absa Bank", r"\babsa\b"), ("Stanbic Bank", r"stanbic"), ("Ecobank", r"eco ?bank"),
         ("Fidelity Bank", r"fidelity"), ("CalBank", r"cal ?bank"), ("Access Bank", r"access bank"), ("Zenith Bank", r"zenith"),
         ("UBA", r"\buba\b"), ("Standard Chartered", r"standard chartered|\bstanchart"), ("Republic Bank", r"republic bank"),
         ("First National Bank", r"\bfnb\b|first national bank"), ("Prudential Bank", r"prudential bank"),
         ("Consolidated Bank Ghana", r"consolidated bank|\bcbg\b"), ("Agricultural Development Bank", r"\badb\b|agricultural development bank"),
         ("National Investment Bank", r"\bnib\b|national investment bank"), ("First Atlantic Bank", r"first atlantic"),
         ("OmniBSIC Bank", r"omni ?bsic"), ("GTBank", r"gt ?bank|guaranty trust"), ("Bank of Africa", r"bank of africa|\bboa\b"),
         ("Universal Merchant Bank", r"\bumb\b|universal merchant"), ("Societe Generale Ghana", r"soci[eé]t[eé] g[eé]n[eé]rale"),
         ("ARB Apex Bank", r"arb apex")]
NETWORKS = {**{p: "MTN MoMo" for p in ("024", "025", "053", "054", "055", "059")},
            **{p: "Telecel Cash" for p in ("020", "050")}, **{p: "AirtelTigo Money" for p in ("026", "027", "056", "057")}}
def network_of(number):
    return NETWORKS.get(re.sub(r"^\+?233", "0", number)[:3], "")
def banks_in(text):
    return [name for name, rx in BANKS if re.search(rx, text, re.I)]
def domain_of(u):
    u = re.sub(r"^(?:https?://|www\.)", "", u.strip().lower()); u = u.split("/")[0].split("?")[0]
    return re.sub(r"^www\.", "", u)
def extract(text):
    digits = re.sub(r"(?<=\d)[ -](?=\d)", "", text)
    ph = PHONE.findall(digits)
    return {
        "momo_numbers": sorted(set(re.sub(r"^\+?233", "0", p) for p in ph)),
        "bank_accounts": sorted(set(a for a in ACCT.findall(digits) if a not in ph and not (a.startswith("233") and len(a) == 12))),
        "links": sorted(set(u.rstrip(".") for u in URL.findall(text))),
        "handles": sorted(set(HANDLE.findall(text))),
        "promised_returns": sorted(set(x.strip() for x in PCT.findall(text))),
        "licence_claimed": sorted(set(LICENCE.findall(text))),
        "account_names": sorted(set(n.strip() for n in NAMEON.findall(text))),
        "banks": banks_in(text),
    }
def merge(a, b):
    return {k: sorted(set(a.get(k, [])) | set(b.get(k, []))) for k in b}
