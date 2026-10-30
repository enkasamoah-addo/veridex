"""Ananse site inspector: looks at a suspect website the way a careful person would, but safely.
It only READS the page text (no scripts run, no forms are submitted, no login), blocks private
network addresses, and limits size/time. Returns plain findings the SEC officer can read.
Checks: domain age (RDAP), lookalike of regulators/known brands, page claims a real licensed firm's name
on an unrelated domain (clone), page asks for MoMo/ID/password, phones and handles on the page."""
import re, os, socket, ipaddress, datetime, time, threading
from urllib.parse import urlparse, urljoin
import httpx
from rapidfuzz import fuzz

LEGIT = {"sec.gov.gh", "bog.gov.gh", "npra.gov.gh", "csa.gov.gh", "gra.gov.gh", "ghana.gov.gh", "gse.com.gh",
         "mtn.com.gh", "goil.com.gh", "telecel.com.gh", "airteltigo.com.gh"}
REGULATOR_WORDS = ("secghana", "ghanasec", "secgov", "bankofghana", "boggov", "bogghana", "npragh", "npraghana",
                   "csaghana", "securitiesandexchange")
SOCIAL = ("t.me", "wa.me", "whatsapp.com", "chat.whatsapp.com", "facebook.com", "fb.com", "instagram.com", "tiktok.com",
          "youtube.com", "youtu.be", "x.com", "twitter.com", "linkedin.com", "telegram.me", "telegram.org")
BAD_TLD = (".xyz", ".top", ".vip", ".club", ".site", ".online", ".icu", ".shop", ".live", ".cc", ".buzz", ".work", ".click")
PHONE = re.compile(r"(?<!\d)(?:\+?233|0)[235]\d{8}(?!\d)")
HANDLE = re.compile(r"(?:t\.me|wa\.me|telegram\.me|chat\.whatsapp\.com|facebook\.com|fb\.com|instagram\.com|tiktok\.com/@|twitter\.com|x\.com|youtube\.com/(?:@|c/|channel/)|linkedin\.com/(?:company|in)/)[A-Za-z0-9_+./-]{2,40}")

_CACHE, _LOCK = {}, threading.Lock()

def _clean(s): return re.sub(r"[^a-z0-9]", "", s.lower())
def _label(domain):
    parts = domain.split(".")
    if len(parts) >= 3 and parts[-2] in ("com", "org", "net", "co", "gov", "edu"): return parts[-3]
    return parts[-2] if len(parts) >= 2 else domain

def _safe_host(host):
    """Refuse localhost/private/link-local targets (SSRF protection). Test override: VERIDEX_ALLOW_PRIVATE=1."""
    if os.environ.get("VERIDEX_ALLOW_PRIVATE"): return True
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    for i in infos:
        ip = ipaddress.ip_address(i[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True

def _fetch(url):
    """Fetch HTML text with manual redirects (max 3), size and time limits. Returns (final_url, status, html)."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; VeridexSiteCheck/1.0; +scam-research)", "Accept": "text/html"}
    for _ in range(4):
        host = urlparse(url).hostname or ""
        if not _safe_host(host): return url, None, ""
        with httpx.stream("GET", url, headers=headers, timeout=6, follow_redirects=False, verify=True) as r:
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                url = urljoin(url, r.headers["location"]); continue
            if "html" not in r.headers.get("content-type", "html").lower(): return url, r.status_code, ""
            buf = b""
            for chunk in r.iter_bytes():
                buf += chunk
                if len(buf) > 400_000: break
            return url, r.status_code, buf.decode(r.encoding or "utf-8", errors="ignore")
    return url, None, ""

def _age_days(domain):
    from core.checker import domain_age_days
    return domain_age_days(domain)

def _text_of(html):
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    title = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    body = re.sub(r"(?s)<[^>]+>", " ", html)
    body = re.sub(r"&nbsp;|&amp;", " ", body)
    return (re.sub(r"\s+", " ", title.group(1)).strip() if title else ""), re.sub(r"\s+", " ", body).strip()

def investigate(url, force=False):
    """Return a dict of findings for one URL. Never raises."""
    from core.idents import domain_of
    if not re.match(r"https?://", url, re.I): url = "http://" + re.sub(r"^www\.", "www.", url)
    dom = domain_of(url)
    with _LOCK:
        hit = _CACHE.get(dom)
        if hit and not force and time.time() - hit[0] < 600: return hit[1]
    r = {"url": url, "domain": dom, "fetched": False, "status": None, "https": url.lower().startswith("https"),
         "age_days": None, "title": "", "snippet": "", "findings": [], "phones": [], "handles": [],
         "impersonates": "", "clone_of": "", "asks_payment": False, "claims_licence": False, "final_domain": dom}
    F = lambda sev, text: r["findings"].append({"sev": sev, "text": text})
    clean = _clean(dom); label = _clean(_label(dom))

    # 1) the web address itself
    if dom.startswith("xn--") or ".xn--" in dom:
        r["impersonates"] = "a real name using look-alike characters"
        F("bad", "The address uses look-alike (international) characters, a common trick to copy a real name.")
    if dom not in LEGIT and not dom.endswith(".gov.gh"):
        if any(w in clean for w in REGULATOR_WORDS):
            r["impersonates"] = "a Ghana regulator"
            F("bad", f"The address ({dom}) copies the name of a Ghana regulator but is not an official .gov.gh website.")
        else:
            toks = [t for t in re.split(r"[^a-z0-9]+", _label(dom).lower()) if t]
            for legit in LEGIT:
                ll = _clean(_label(legit))
                if ll == "ghana": continue                    # too generic to mean anything
                typo = len(ll) >= 4 and label != ll and fuzz.ratio(label, ll) >= 82
                brand_word = ll in toks and label != ll       # e.g. mtn-invest, goil-bonus
                if typo or brand_word:
                    r["impersonates"] = legit
                    F("bad", f"The address ({dom}) looks like the real {legit} but is a different website.")
                    break
    if any(dom.endswith(t) for t in BAD_TLD):
        F("warn", f"The address ends in '{dom[dom.rfind('.'):]}', an extension cheap scam sites often use.")
    age = _age_days(dom); r["age_days"] = age
    if age is not None:
        if age < 90: F("bad", f"The website was created only {age} days ago.")
        elif age < 365: F("warn", f"The website is less than a year old ({age} days).")
        else: F("ok", f"The website was created {age // 365} year(s) ago.")
    else:
        F("info", "We could not look up when this website was created.")

    # 2) what the page says
    try:
        final, status, html = _fetch(url)
        r["status"] = status; r["fetched"] = bool(html)
        r["final_domain"] = domain_of(final)
        if r["final_domain"] != dom: F("warn", f"The link redirects to a different website ({r['final_domain']}).")
        if html:
            title, text = _text_of(html)
            r["title"], r["snippet"] = title[:140], text[:400]
            low = (title + " " + text).lower()
            r["phones"] = sorted(set(re.sub(r"^\+?233", "0", p) for p in PHONE.findall(re.sub(r"(?<=\d)[ -](?=\d)", "", text))))[:6]
            r["handles"] = sorted(set(HANDLE.findall(html)))[:6]
            if re.search(r"guarantee|risk[- ]free|no risk|double your|daily (profit|return)|weekly (profit|return)|\d{2,4}\s?% (daily|weekly|monthly)", low):
                F("bad", "The page promises guaranteed or very high profit.")
            if re.search(r"mobile money|momo|send (money|payment) to|deposit (via|using|with)", low) or re.search(r"type=[\"']?password", html, re.I) \
               or re.search(r"ghana card|pin number|otp|verification code", low):
                r["asks_payment"] = True
                F("bad", "The page asks for mobile money payment, or for ID details, a PIN/OTP or a password.")
            if re.search(r"sec (licen[cs]ed|registered|licen[cs]e)|licen[cs]ed by (the )?sec|licen[cs]e (no|number)", low):
                r["claims_licence"] = True
                F("warn", "The page says it is licensed or registered. Always confirm that with the SEC itself.")
            # clone check: page uses the name of a firm on our licensed list, but the address is not theirs
            from core import checker
            m = checker.match_entity(title + ". " + text[:2500])
            if m and m["type"] == "LICENSED":
                toks = [t for t in checker.norm(m["name"]).split() if len(t) >= 5]
                if not any(t in clean for t in toks):
                    r["clone_of"] = m["name"]
                    F("bad" if (age is not None and age < 365) else "warn",
                      f"The page uses the name of the licensed firm '{m['name']}', but this web address is not theirs. Scammers copy real firms like this.")
            if r["phones"]: F("info", "Phone numbers on the page: " + ", ".join(r["phones"]))
        elif status is None:
            F("info", "We could not open the page (it may be down or blocked).")
    except Exception as e:
        F("info", "We could not open the page (it may be down or blocked).")
    with _LOCK: _CACHE[dom] = (time.time(), r)
    return r

def skip(domain):
    return domain in SOCIAL or domain.endswith(".gov.gh") or domain in LEGIT or any(domain.endswith("." + s) for s in SOCIAL)
