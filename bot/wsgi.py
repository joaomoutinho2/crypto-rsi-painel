from bot_rsi import app, iniciar_bot
import threading
threading.Thread(target=iniciar_bot, daemon=True).start()
