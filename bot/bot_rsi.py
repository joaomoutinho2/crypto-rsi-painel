# bot.py – Versão pronta para Render (Web Service)
# --------------------------------------------------
# Arranca rapidamente o servidor Flask para satisfazer o health‑check
# e corre o bot de análise de criptos em segundo‑plano.
# --------------------------------------------------

import os
import threading
import time
from datetime import datetime

import requests
from flask import Flask

# Carregamento leve: bibliotecas pesadas (ccxt, pandas, ta, joblib, etc.)
# são importadas SOMENTE dentro da thread de background, para não atrasar
# o arranque do servidor HTTP.

# --------------------------------------------------
# Configurações
# --------------------------------------------------
TIMEFRAME = os.getenv("TIMEFRAME", "1h")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
MODELO_PATH = "modelo/modelo_treinado.pkl"
INTERVALO_RESUMO_HORAS = 2
MAX_ALERTAS_POR_CICLO = 5

# --------------------------------------------------
# Servidor Flask (Web Service)
# --------------------------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    """Endpoint simples para o health‑check do Render."""
    return "✅ Bot RSI com modelo ativo."

@app.route("/treinar_modelo")
def treinar_modelo():
    """Treina novamente o modelo, se necessário."""
    try:
        from modelo.treino_modelo_firebase import atualizar_resultados_firestore
        atualizar_resultados_firestore()
        return "✅ Modelo treinado com sucesso!"
    except Exception as e:
        return f"❌ Erro ao treinar modelo: {e}"

# --------------------------------------------------
# Funções utilitárias
# --------------------------------------------------

def enviar_telegram(mensagem: str):
    """Envia mensagem via Telegram, se o token/chat estiverem configurados."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Telegram não configurado – mensagem:", mensagem)
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": mensagem})
    except Exception as exc:
        print(f"❌ Erro ao enviar Telegram: {exc}")

# --------------------------------------------------
# Thread de Background – Bot de análise
# --------------------------------------------------

def thread_bot():
    """Carrega dependências pesadas e inicia o ciclo infinito de análise."""
    print("🤖 Thread do bot a iniciar… (pode demorar um pouco)")

    # Importações pesadas aqui para não atrasar o Flask
    import ccxt
    import pandas as pd
    from ta.momentum import RSIIndicator
    from ta.trend import EMAIndicator, MACD
    from ta.volatility import BollingerBands
    import joblib

    from utils.firebase_config import iniciar_firebase

    # --------------------------------------------------
    # Inicializar Firebase
    # --------------------------------------------------
    try:
        db = iniciar_firebase()
        print("✅ Firebase inicializado")
    except Exception as exc:
        print(f"⚠️  Firebase não inicializou: {exc}")
        db = None

    # --------------------------------------------------
    # Carregar Modelo
    # --------------------------------------------------
    modelo = None
    try:
        modelo = joblib.load(MODELO_PATH)
        print("✅ Modelo carregado de", MODELO_PATH)
    except Exception as exc:
        print(f"⚠️  Não foi possível carregar modelo: {exc}")

    # --------------------------------------------------
    # Funções internas que dependem de libs pesadas
    # --------------------------------------------------

    def guardar_previsao_firestore(registo: dict):
        if db is None:
            return
        try:
            db.collection("historico_previsoes").add(registo)
        except Exception as exc:
            print(f"❌ Firestore previsões: {exc}")

    def guardar_estrategia_firestore(reg: dict):
        if db is None:
            return
        try:
            db.collection("estrategias").add(reg)
        except Exception as exc:
            print(f"❌ Firestore estratégias: {exc}")

    # --------------------------------------------------
    # Lógica principal do bot
    # --------------------------------------------------

    exchange = ccxt.kucoin()
    exchange.load_markets()
    moedas = [s for s in exchange.symbols if s.endswith("/USDT")]

    ultimo_resumo = datetime.now()

    while True:
        oportunidades = []
        for moeda in moedas:
            try:
                candles = exchange.fetch_ohlcv(moeda, timeframe=TIMEFRAME, limit=100)
                df = pd.DataFrame(
                    candles, columns=["timestamp", "open", "high", "low", "close", "volume"]
                )

                # Indicadores
                df["RSI"] = RSIIndicator(close=df["close"]).rsi()
                ema = EMAIndicator(close=df["close"]).ema_indicator()
                macd = MACD(close=df["close"])
                df["EMA"] = ema
                df["MACD"] = macd.macd()
                df["MACD_signal"] = macd.macd_signal()
                df["volume_medio"] = df["volume"].rolling(window=14).mean()
                bb = BollingerBands(close=df["close"])
                df["BB_lower"] = bb.bollinger_lband()
                df["BB_upper"] = bb.bollinger_hband()

                # Último valor
                rsi = df["RSI"].iat[-1]
                preco = df["close"].iat[-1]
                ema_val = df["EMA"].iat[-1]
                macd_val = df["MACD"].iat[-1]
                macd_sig = df["MACD_signal"].iat[-1]
                vol = df["volume"].iat[-1]
                vol_med = df["volume_medio"].iat[-1] or 1
                bb_inf = df["BB_lower"].iat[-1]
                bb_sup = df["BB_upper"].iat[-1]

                entrada = pd.DataFrame([
                    {
                        "RSI": rsi,
                        "EMA_diff": (preco - ema_val) / ema_val,
                        "MACD_diff": macd_val - macd_sig,
                        "Volume_relativo": vol / vol_med,
                        "BB_position": (preco - bb_inf) / (bb_sup - bb_inf) if bb_sup > bb_inf else 0.5,
                    }
                ])

                previsao = bool(modelo.predict(entrada)[0]) if modelo else False

                registo = {
                    "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Moeda": moeda,
                    "RSI": rsi,
                    "EMA_diff": entrada["EMA_diff"].iat[0],
                    "MACD_diff": entrada["MACD_diff"].iat[0],
                    "Volume_relativo": entrada["Volume_relativo"].iat[0],
                    "BB_position": entrada["BB_position"].iat[0],
                    "Previsao": int(previsao),
                }
                guardar_previsao_firestore(registo)

                if previsao:
                    msg = f"🚨 {moeda}: RSI={rsi:.2f} MACD={macd_val:.2f}/{macd_sig:.2f}"
                    oportunidades.append((abs(registo["MACD_diff"]), msg))
                    guardar_estrategia_firestore({
                        "Moeda": moeda,
                        "Direcao": "ENTRADA",
                        "Preço": preco,
                        "RSI": rsi,
                        "Data": registo["Data"],
                    })

            except Exception as exc:
                print(f"⚠️  Erro a analisar {moeda}: {exc}")

        # Enviar TOP oportunidades
        oportunidades.sort(reverse=True)
        for _, msg in oportunidades[:MAX_ALERTAS_POR_CICLO]:
            enviar_telegram(msg)

        # Resumo periódico (se quiseres)
        agora = datetime.now()
        if (agora - ultimo_resumo).total_seconds() > INTERVALO_RESUMO_HORAS * 3600:
            enviar_telegram("Resumo: ciclo concluído com " + str(len(oportunidades)) + " alertas")
            ultimo_resumo = agora

        time.sleep(3600)  # espera 1 h

# --------------------------------------------------
# Arranque da aplicação
# --------------------------------------------------
if __name__ == "__main__":
    # 1️⃣  Inicia o bot em segundo‑plano (não bloqueia)
    threading.Thread(target=thread_bot, daemon=True).start()

    # 2️⃣  Inicia o Flask – Render detectará a porta já aberta
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 Flask a ouvir em 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
