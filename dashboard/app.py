"""SEC officer dashboard.  streamlit run dashboard/app.py"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import streamlit as st, pandas as pd
import db
from zeus.honeypot import Session
from zeus.scammer_sim import SCRIPT
st.set_page_config(page_title="SEC Scam Desk", layout="wide")
st.title("Veridex · SEC Scam Desk")
st.caption("Citizen reports + Ananse honeypot evidence. Every action needs an officer's approval.")
cases = db.all_cases()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Cases", len(cases)); c2.metric("High risk", sum(c["level"] == "RED" for c in cases))
c3.metric("Ananse cases", sum(c["source"] == "zeus" for c in cases)); c4.metric("Awaiting review", sum(c["status"] in ("new", "reported_by_user") for c in cases))
with st.sidebar:
    st.subheader("Ananse demo")
    st.write("Runs the honeypot against a **simulated** scammer (never real contacts).")
    if st.button("Run Ananse on simulated scam"):
        s = Session(SCRIPT[0], channel="simulation", source="zeus", user_ref="demo")
        for m in SCRIPT[1:]:
            s.reply(); s.hear(m)
        s.file_case(); st.rerun()
if not cases:
    st.info("No cases yet. Message the Telegram bot or run Ananse.")
else:
    df = pd.DataFrame([{k: c[k] for k in ("id", "created", "source", "channel", "level", "entity", "status")} for c in cases])
    st.dataframe(df, use_container_width=True, hide_index=True)
    sel = st.selectbox("Open case", [c["id"] for c in cases])
    c = next(x for x in cases if x["id"] == sel)
    a, b = st.columns(2)
    with a:
        st.subheader(f"Case #{c['id']}: {c['level']}")
        for r in json.loads(c["reasons"]): st.write("• " + r)
        ev = json.loads(c["evidence"])
        if any(ev.values()):
            st.markdown("**Evidence captured by Ananse**"); st.json({k: v for k, v in ev.items() if v})
    with b:
        tr = json.loads(c["transcript"])
        if tr:
            st.markdown("**Conversation**")
            for t in tr: st.chat_message("assistant" if t["role"] == "zeus" else "user").write(t["text"])
        else:
            st.markdown("**Message received**"); st.write(c["text"])
    st.divider(); st.markdown("**Officer actions (human approval)**")
    x1, x2, x3 = st.columns(3)
    if x1.button("Approve public warning"): db.update(sel, status="warning_approved", action="Public warning drafted"); st.rerun()
    if x2.button("Request MoMo number flag"): db.update(sel, status="momo_flag_requested", action="Flag request to telco/BoG"); st.rerun()
    if x3.button("Refer to CSA / Police"): db.update(sel, status="referred", action="Referred to CSA"); st.rerun()
    st.caption(f"Status: {c['status']} {('| ' + c['action']) if c['action'] else ''}")
