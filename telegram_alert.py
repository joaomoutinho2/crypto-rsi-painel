"""
📨 Módulo de Envio de Alertas via Telegram

Esta função é usada para enviar mensagens formatadas para um chat ou grupo específico via API do Telegram.
Requer as variáveis de ambiente TELEGRAM_TOKEN e TELEGRAM_CHAT_ID corretamente definidas.
"""

import os
import requests

def enviar_telegram(mensagem):
    """
    Envia uma mensagem para o Telegram usando a API Bot.

    Parâmetros:
    - mensagem (str): Texto da mensagem a enviar
    """
    try:
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            raise ValueError("TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID não definidos.")

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": mensagem
        }
        response = requests.post(url, data=payload)

        if response.status_code != 200:
            raise Exception(f"Erro ao enviar mensagem: {response.text}")

    except Exception as e:
        print(f"❌ Erro ao enviar Telegram: {e}")
