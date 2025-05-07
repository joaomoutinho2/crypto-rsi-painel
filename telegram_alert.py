import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensagem
    }
    try:
        response = requests.post(url, data=data)
        if response.status_code != 200:
            print("❌ Erro Telegram:", response.text)
    except Exception as e:
        print("❌ Exceção Telegram:", e)
