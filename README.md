# 🕸️ Veridex

**A 24/7, 6-language scam-check and investigation system for Ghana's SEC.**

Citizens check an investment offer — or report one — in Telegram, on the web, or by phone, in their own language. If it looks like a scam, an AI honeypot (**Ananse**) engages the scammer directly to extract evidence, while a live case dashboard pushes verified cases straight to SEC's own systems.

🏆 **3rd Place — SEC-ALX Virtual & Digital Assets Hackathon**

[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![Languages](https://img.shields.io/badge/languages-6%20Ghanaian%20languages-FCD116)](#)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## The problem

Online investment fraud in Ghana is accelerating, and it's happening mostly on the apps people already trust:

- **GH¢3.4 million** lost to online investment fraud in just the **first half of 2026** — 352 reported cases (Cyber Security Authority, Ghana).
- Up from **GH¢1.99 million** (Jan–Aug 2024) and **GH¢421,621** (2023) — the trend is accelerating, not slowing down.
- Scammers recruit through unsolicited **WhatsApp and Telegram groups**, promise guaranteed daily/monthly returns, and vanish once victims try to withdraw.
- SEC Ghana's current public complaint channel is a static web form that requires reporting to the operator first and waiting **30 days** before SEC even gets involved — with no confirmation, case number, or tracking.

Veridex exists to close that gap: instant checking, automated evidence-gathering, and a direct, auditable pipeline into SEC's own case-management workflow.

## What it does

| Capability | Description |
|---|---|
| **Instant scam check** | A rule-based verdict engine checks any offer against real, published SEC/BoG/NPRA registers — licensed firms, revoked licences, unlicensed-entity warnings. Never an AI guess. |
| **Ananse (AI honeypot)** | Once a scammer makes contact, Ananse — an AI investigator persona — keeps them talking, pulling out MoMo numbers, bank details, claimed licence numbers, and links, logged live to an evidence notebook. |
| **6 Ghanaian languages** | English, Twi, Ga, Ewe, Fante, Dagbani — text and synthesized voice, powered by GhanaNLP's Khaya API. |
| **Multi-channel intake** | Telegram bot, web widget, and a phone/IVR line (Africa's Talking), so no citizen is locked out by data cost or literacy. |
| **SEC case dashboard** | Live queue of checks, flagged cases, and evidence-ready cases, each with a one-click PDF case report. |
| **Direct-to-SEC delivery** | Every "evidence ready" case is automatically pushed to SEC's own systems — via an authenticated, HMAC-signed webhook, or a structured PDF email — the same integration pattern used by fraud/AML platforms like Flagright and Stripe Radar, not a novel or fragile mechanism. |

## Screenshots

**Landing page**
![Landing page](assets/screenshots/landing.jpg)

**Telegram — language picker (6 Ghanaian languages)**
![Telegram language picker](assets/screenshots/telegram-language.jpg)

**Telegram — AI verdict in Twi, with an SEC-escalation button**
![Telegram verdict in Twi](assets/screenshots/telegram-verdict.jpg)

**Telegram — spoken verdict as a Twi voice note**
![Telegram Twi voice note](assets/screenshots/telegram-voicenote.jpg)

**SEC case dashboard — live overview**
![SEC dashboard overview](assets/screenshots/dashboard-overview.jpg)

**Ananse — the honeypot engages a scammer, live**
![Ananse live chat](assets/screenshots/ananse-chat-start.jpg)

**Ananse's notebook — evidence extracted mid-conversation**
![Ananse evidence notebook](assets/screenshots/ananse-evidence.jpg)

**Dashboard — case flagged "Evidence ready," PDF report generated**
![Evidence ready case](assets/screenshots/dashboard-evidence-ready.jpg)

**IVR phone line — language menu**
![IVR language menu](assets/screenshots/ivr-menu.jpg)

**IVR phone line — in Twi**
![IVR dialpad in Twi](assets/screenshots/ivr-dialpad.jpg)

## Architecture
