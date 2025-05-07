import requests

# Substitui pelos teus dados
BOT_TOKEN = '7565501884:AAEdjbr_0taJqxaeY443wS9fjlfpVQ7Whp0'
CHAT_ID = '6952850816'

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": mensagem
    }
    try:
        response = requests.post(url, data=data)
        if response.status_code != 200:
            print("Erro ao enviar mensagem para o Telegram.")
    except Exception as e:
        print("Erro:", e)
