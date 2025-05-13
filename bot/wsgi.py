import os
import threading
from bot.bot_rsi import app, iniciar_bot

if __name__ == "__main__":
    # Inicia o bot em background
    threading.Thread(target=iniciar_bot, daemon=True).start()

    # Porta fornecida pelo Render
    port = int(os.environ.get("PORT", 10000))

    # Gunicorn não usa este bloco, mas serve de fallback
    app.run(host="0.0.0.0", port=port)

# Para o Gunicorn:
# o objeto WSGI é `app` importado abaixo
