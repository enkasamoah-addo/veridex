# Starts the API (with Ananse) and the Telegram bot in two windows. Keys are read from .env
Set-Location $PSScriptRoot
Start-Process powershell -ArgumentList '-NoExit','-Command','python -m uvicorn api.main:app --port 8000'
Start-Sleep -Seconds 3
Start-Process powershell -ArgumentList '-NoExit','-Command','python bot/telegram_bot.py'
Write-Host "Started. Open http://localhost:8000/dashboard.html and http://localhost:8000/ananse.html"
