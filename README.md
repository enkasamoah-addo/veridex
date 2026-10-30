# Veridex: scam-check + Ananse 
Run on your laptop (Python 3.10+):
  pip install -r requirements.txt
  python core/checker.py "Invest in QX Broker 20% daily guaranteed"      # test the checker
  streamlit run dashboard/app.py                                          # SEC desk + "Run Ananse" button
  PowerShell: $env:TELEGRAM_BOT_TOKEN="..." (from @BotFather)
  PowerShell: $env:GROQ_API_KEY="..." (free: console.groq.com  (or GEMINI_API_KEY from aistudio.google.com)
  PowerShell: $env:KHAYA_API_KEY="..." (free: translation.ghananlp.org)
  python bot/telegram_bot.py
Without GROQ/GEMINI key Ananse uses staged questions; without KHAYA key the bot replies in English only.
Data: data/*.csv (real SEC/NPRA). To upgrade GREEN verdicts, add the live SEC register CSV and load it in core/checker.py.
Khaya codes for Ga/Ewe/Fante in core/voice.py are UNVERIFIED: check the Khaya languages page.
