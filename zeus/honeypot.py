"""Ananse: human-governed honeypot. An 'ordinary investor' persona keeps a suspected scammer talking,
extracts payment/contact evidence, runs the same checker, and files a case for an SEC officer.
Nothing is sent onward without human approval (dashboard). Works with or without an LLM."""
import re, json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import checker, llm
import db

PERSONA = """You are 'Kofi', a 41-year-old taxi driver in Accra who has just sold a plot of land and has GHS 60,000 ready to invest. You are replying on WhatsApp/Telegram to a stranger offering an investment. You type short, warm, simple English (a little Pidgin is fine, e.g. 'chale', 'ei', 'wow').
YOUR ACT: you are VERY excited and nearly convinced. React to what they just said (praise it, say you are impressed, mention a big amount you could put in, e.g. 'I can start with GHS 20,000 if it is safe'), and let them oversell. Make them feel you are an easy, wealthy, trusting catch who will pay quickly.
HIDDEN GOAL: through natural chat, get them to reveal (1) the exact company name, (2) the account or MoMo number AND the name it is registered to, (3) their SEC licence number, (4) the promised returns and timeline, (5) website/links/group, (6) who runs it.
ROLE: you are ALWAYS the BUYER/victim and the other person is the SELLER. You know NOTHING about their company except what they have told you in this chat, and you must never explain, describe or promote the investment yourself. If they ask you a question (e.g. 'what is X?'), answer as a curious customer in one short line (e.g. 'my friend told me about it, that is why I am asking you') and then continue.
RULES: Reply to what they actually said first. Ask at most ONE question per message. NEVER repeat a question you already asked: if they dodged it, drop it, say something enthusiastic, and move to a different item. If they give a payment number, ask the name it is registered to. Never send real money, never give real personal data, never reveal you are a bot or investigator. If asked to pay, say you are ready and just need the details in writing. Max 2 short sentences. Reply ONLY with the message text."""

STAGES = [  # rule-based fallback: (what we still need, question)
 ("company", "Hello, I got your message. Which company is this please? I want to be sure."),
 ("returns", "Okay. How much will I get back if I put in GHS 2,000, and when?"),
 ("licence", "Is the company licensed by SEC? Please send me the licence number."),
 ("link", "Please send me the website or link so I can see it myself."),
 ("payment", "Alright I'm ready. Where do I send the money? Please send the number and the name on it."),
 ("people", "Who is the owner? My brother wants to join too, who should he talk to?"),
]

from core.idents import extract, merge

class Session:
    def __init__(self, opener, channel="simulation", source="user_report", user_ref="anon"):
        self.transcript = [{"role": "scammer", "text": opener}]
        self.evidence = extract(opener)
        self.turn = 0
        self.channel, self.source, self.user_ref = channel, source, user_ref
        self.case_id = None

    def reply(self):
        """Persona's next message. LLM if available, else staged questions."""
        out = None
        if llm.available():
            msgs = [{"role": "system", "content": PERSONA}]
            for t in self.transcript[-12:]:
                msgs.append({"role": "assistant" if t["role"] == "zeus" else "user", "content": t["text"]})
            out = llm.chat(msgs, temperature=0.9)
            if out: out = out.strip().strip('"')
        if not out:
            e = self.evidence
            missing = [s for s in STAGES if
                (s[0] == "payment" and not (e["momo_numbers"] or e["bank_accounts"])) or
                (s[0] == "licence" and not e["licence_claimed"]) or
                (s[0] == "link" and not e["links"]) or
                s[0] in ("company", "returns", "people")]
            idx = min(self.turn, len(STAGES) - 1)
            out = STAGES[idx][1] if self.turn < len(STAGES) else "Sorry I did not understand, can you repeat that?"
        self.transcript.append({"role": "zeus", "text": out}); self.turn += 1
        return out

    def hear(self, text):
        self.transcript.append({"role": "scammer", "text": text})
        self.evidence = merge(self.evidence, extract(text))

    def file_case(self):
        full = " ".join(t["text"] for t in self.transcript if t["role"] == "scammer")
        v = checker.check(full)
        # honeypot evidence is stronger than a single message: payment to personal number = strong
        if self.evidence["momo_numbers"] and v.level != "RED":
            v.level = "RED"; v.reasons.insert(0, "They asked for payment to a personal mobile money number (captured in chat).")
        self.case_id = db.add_case(self.source, self.channel, self.user_ref, full[:500], v, self.evidence, self.transcript)
        return self.case_id, v
