import threading
from bot.bot_rsi import app, iniciar_bot

# Inicia o loop do bot em background
threading.Thread(target=iniciar_bot, daemon=True).start()

# O Gunicorn vai usar o objeto WSGI `app`
