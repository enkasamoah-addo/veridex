// One place for the switches you may want to change.
window.VERIDEX = {
  TELEGRAM_URL: "https://t.me/veridexgh_bot",
  API_BASE: location.protocol.startsWith("http") ? location.origin : "http://localhost:8000",   // same address the page was served from; set to your hosted API address if the site lives elsewhere
  WHATSAPP_LIVE: false,                // true once the WhatsApp bot works; then set WHATSAPP_URL
  WHATSAPP_URL: "",
  USSD_LIVE: false,                    // true once a real USSD code / toll-free line exists
  SHOW_BACKED_BY: false                // ONLY set true after the SEC / BoG / CSA confirm in writing that they back Veridex
};
