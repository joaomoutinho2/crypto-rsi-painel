import requests
from utils.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def enviar_telegram(mensagem):
    """
    Envia uma mensagem para o chat do Telegram usando a API do bot.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensagem
    }
    try:
        response = requests.post(url, data=data)
        if response.status_code != 200:
            print("❌ Erro Telegram:", response.status_code, response.text)
    except Exception as e:
        print("❌ Exceção Telegram:", e)
