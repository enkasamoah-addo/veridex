"""Loads keys from a local .env file (never committed to git) so you do not retype them every time."""
import os
def load():
    p = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(p): return
    for line in open(p, encoding="utf-8-sig"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
