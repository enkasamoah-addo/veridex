"""Veridex API. Run:  uvicorn api.main:app --reload --port 8000   (docs at /docs)
The landing page, SEC dashboard and bots all use this."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import env; env.load()
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
import db
from core import checker
from zeus import hunter, engine
import threading

app = FastAPI(title="Veridex API")
_STOP = threading.Event()

@app.on_event("startup")
def _start_ananse():
    """Ananse works by himself: every flagged check is picked up here within seconds."""
    threading.Thread(target=engine.worker, args=(_STOP,), daemon=True).start()

@app.on_event("shutdown")
def _stop_ananse(): _STOP.set()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class CheckIn(BaseModel):
    text: str
    channel: str = "web"
class MsgIn(BaseModel):
    text: str
class ActionIn(BaseModel):
    action: str   # warning_approved | momo_flag_requested | referred | dismissed

def verdict_json(v):
    return {"level": v.level, "headline": v.headline, "checks": [{"icon": i, "label": l} for i, l in v.checks],
            "reasons": v.reasons, "do_now": v.do_now, "comfort": v.comfort, "flags": v.flags,
            "matched": v.matched, "sources": v.sources, "spoken": checker.spoken(v)}

def case_json(c, full=False):
    out = {k: c[k] for k in ("id", "created", "source", "channel", "level", "entity", "status", "action")}
    out["reasons"] = json.loads(c["reasons"] or "[]"); out["flags"] = json.loads(c["flags"] or "[]")
    out["evidence"] = json.loads(c["evidence"] or "{}")
    if full: out["transcript"] = json.loads(c["transcript"] or "[]"); out["text"] = c["text"]
    return out

@app.get("/api/health")
def health(): return {"ok": True}

@app.post("/api/check")
def check(body: CheckIn):
    v = checker.check(body.text)
    cid = db.add_case("web_user", body.channel, "web", body.text[:500], v)
    return {**verdict_json(v), "case_id": cid}

@app.get("/api/stats")
def stats(): return db.stats()

@app.get("/api/cases")
def cases(): return [case_json(c) for c in db.all_cases()]

@app.get("/api/cases/{cid}")
def case(cid: int):
    c = db.get_case(cid)
    if not c: raise HTTPException(404, "no such case")
    return case_json(c, full=True)

@app.post("/api/cases/{cid}/ananse")
def run_ananse(cid: int):
    if not db.get_case(cid): raise HTTPException(404, "no such case")
    return case_json(hunter.engage(cid), full=True)

@app.get("/api/live")
def live():
    """Conversations Ananse is in right now (for the WhatsApp-style demo chat)."""
    out = []
    for c in db.all_cases():
        if c["status"] in engine.ACTIVE:
            ev = json.loads(c["evidence"] or "{}"); tr = json.loads(c["transcript"] or "[]")
            contact = next(iter(ev.get("handles", []) + ev.get("momo_numbers", []) + ev.get("links", [])), "Suspected scammer")
            out.append({"id": c["id"], "entity": c["entity"], "status": c["status"], "contact": contact, "messages": len(tr)})
    return out

@app.post("/api/cases/{cid}/scammer_message")
def scammer_message(cid: int, body: MsgIn):
    if not db.get_case(cid): raise HTTPException(404, "no such case")
    try: return case_json(engine.on_scammer_message(cid, body.text[:1000]), full=True)
    except ValueError as e: raise HTTPException(409, str(e))

@app.post("/api/cases/{cid}/sim_scammer")
def sim_scammer(cid: int):
    """Solo demo helper: a SIMULATED scammer sends the next scripted line."""
    if not db.get_case(cid): raise HTTPException(404, "no such case")
    try: return case_json(engine.on_scammer_message(cid, engine.sim_scammer_line(cid)), full=True)
    except ValueError as e: raise HTTPException(409, str(e))

@app.post("/api/cases/{cid}/action")
def action(cid: int, body: ActionIn):
    labels = {"warning_approved": "Public warning drafted", "momo_flag_requested": "Flag request sent to telco/BoG",
              "referred": "Referred to Cyber Security Authority", "dismissed": "Dismissed by officer"}
    if body.action not in labels: raise HTTPException(400, "unknown action")
    if not db.get_case(cid): raise HTTPException(404, "no such case")
    db.update(cid, status=body.action, action=labels[body.action])
    return case_json(db.get_case(cid), full=True)

@app.post("/api/watchlist/seed")
def seed(): return {"added": hunter.seed_watchlist()}


# Serve the landing page at http://localhost:8000/  (must stay LAST so /api routes win)
_LANDING = os.path.join(os.path.dirname(__file__), "..", "landing")
if os.path.isdir(_LANDING):
    app.mount("/", StaticFiles(directory=_LANDING, html=True), name="landing")
