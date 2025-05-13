# bot/bot.py – versão para Render (Web Service)
# --------------------------------------------------------------
# ✔ Mantém toda a lógica original do teu bot
# ✔ Flask sobe imediatamente (health-check passa)
# ✔ Firebase + modelo carregados em thread de fundo
# --------------------------------------------------------------

import os
import time
import threading
from datetime import datetime

import ccxt
import pandas as pd
import joblib
import requests
from flask import Flask
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands

from utils.config import TIMEFRAME, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from utils.firebase_config import iniciar_firebase
from modelo.treino_modelo_firebase import modelo as modelo_inicial

# 🔹 Variáveis globais preenchidas na thread do bot
db = None
modelo = None
MODELO_PATH = "modelo/modelo_treinado.pkl"

# Constantes originais
QUEDA_LIMITE = 0.95
OBJETIVO_PADRAO = 10
INTERVALO_RESUMO_HORAS = 2
MAX_ALERTAS_POR_CICLO = 5
ULTIMO_RESUMO = datetime.now() - pd.to_timedelta(INTERVALO_RESUMO_HORAS, unit="h")

# --------------------------------------------------
# Servidor Flask (levanta-se primeiro)
# --------------------------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot RSI ativo."

@app.route("/treinar_modelo")
def treinar_modelo():
    global modelo
    try:
        from modelo.treino_modelo_firebase import atualizar_resultados_firestore, modelo as novo
        atualizar_resultados_firestore()
        modelo = novo
        return "✅ Modelo treinado com sucesso!"
    except Exception as e:
        return f"❌ Erro ao treinar modelo: {e}"

# --------------------------------------------------
# Utilitário Telegram
# --------------------------------------------------

def enviar_telegram(mensagem: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Telegram não configurado –", mensagem)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": mensagem})
    except Exception as exc:
        print(f"❌ Telegram: {exc}")

# --------------------------------------------------
# Firestore helpers
# --------------------------------------------------

def guardar_previsao_firestore(reg):
    if db is None:
        return
    try:
        db.collection("historico_previsoes").add(reg)
    except Exception as exc:
        print(f"❌ Firestore previsões: {exc}")

def guardar_estrategia_firestore(moeda, direcao, preco, sinais, rsi, variacao):
    if db is None:
        return
    try:
        db.collection("estrategias").add({
            "Moeda": moeda,
            "Direcao": direcao,
            "Preço": preco,
            "Sinais": sinais,
            "RSI": rsi,
            "Variação (%)": variacao,
            "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    except Exception as exc:
        print(f"❌ Firestore estratégias: {exc}")

def carregar_posicoes():
    if db is None:
        return []
    return [doc.to_dict() for doc in db.collection("posicoes").stream()]

# --------------------------------------------------
# Core do bot
# --------------------------------------------------

def analisar_oportunidades(exchange, moedas):
    oportunidades = []
    for moeda in moedas:
        try:
            candles = exchange.fetch_ohlcv(moeda, timeframe=TIMEFRAME, limit=100)
            df = pd.DataFrame(candles, columns=["t", "open", "high", "low", "close", "volume"])
            df["RSI"] = RSIIndicator(close=df["close"]).rsi()
            df["EMA"] = EMAIndicator(close=df["close"]).ema_indicator()
            macd_obj = MACD(close=df["close"])
            df["MACD"] = macd_obj.macd()
            df["MACD_signal"] = macd_obj.macd_signal()
            df["vol_med"] = df["volume"].rolling(14).mean()
            bb = BollingerBands(close=df["close"])
            df["BB_inf"] = bb.bollinger_lband()
            df["BB_sup"] = bb.bollinger_hband()

            rsi = df["RSI"].iat[-1]
            preco = df["close"].iat[-1]
            ema = df["EMA"].iat[-1]
            macd = df["MACD"].iat[-1]
            macd_sig = df["MACD_signal"].iat[-1]
            vol = df["volume"].iat[-1]
            vol_med = df["vol_med"].iat[-1] or 1
            bb_inf = df["BB_inf"].iat[-1]
            bb_sup = df["BB_sup"].iat[-1]

            entrada = pd.DataFrame([{ 
                "RSI": rsi,
                "EMA_diff": (preco - ema) / ema,
                "MACD_diff": macd - macd_sig,
                "Volume_relativo": vol / vol_med,
                "BB_position": (preco - bb_inf) / (bb_sup - bb_inf) if bb_sup > bb_inf else 0.5,
            }])
            prev = bool(modelo.predict(entrada)[0]) if modelo else False

            reg = {
                "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Moeda": moeda,
                **entrada.iloc[0].to_dict(),
                "Previsao": int(prev),
                "resultado": None,
            }
            guardar_previsao_firestore(reg)

            if prev:
                sinais = ", ".join([s for s in [
                    "RSI<30" if rsi < 30 else None,
                    "preço>EMA" if preco > ema else None,
                    "MACD>sinal" if macd > macd_sig else None,
                    "vol alto" if vol > vol_med else None,
                    "BB inf" if preco < bb_inf else None,
                ] if s])
                guardar_estrategia_firestore(moeda, "ENTRADA", preco, sinais, rsi, (preco - ema) / ema * 100)
                oportunidades.append((abs(reg["MACD_diff"]), f"🚨 {moeda}: RSI={rsi:.2f} MACD={macd:.2f}/{macd_sig:.2f}"))

        except Exception as exc:
            print(f"⚠️  {moeda}: {exc}")

    oportunidades.sort(reverse=True)
    for _, msg in oportunidades[:MAX_ALERTAS_POR_CICLO]:
        enviar_telegram(msg)

def acompanhar_posicoes(exchange, posicoes):
    global ULTIMO_RESUMO
    agora = datetime.now()
    linhas = []
    for pos in posicoes:
        try:
            ticker = exchange.fetch_ticker(pos["moeda"])
            preco_atual = ticker["last"]
            valor_atual = preco_atual * (pos["montante"] / pos["preco_entrada"])
            lucro = valor_atual - pos["montante"]
            percent = (lucro / pos["montante"]) * 100
            linhas.append(f"{pos['moeda']}: {percent:.2f}%")
        except Exception:
            pass
    if (agora - ULTIMO_RESUMO).total_seconds() > INTERVALO_RESUMO_HORAS * 3600:
        if linhas:
            enviar_telegram("\n".join(linhas))
        ULTIMO_RESUMO = agora

def atualizar_documentos_firestore():
    if db is None:
        return
    try:
        for doc in db.collection("historico_previsoes").stream():
            if "resultado" not in doc.to_dict():
                db.collection("historico_previsoes").document(doc.id).set({"resultado": None}, merge=True)
    except Exception as exc:
        print(f"❌ Atualizar docs: {exc}")

# --------------------------------------------------
# Thread do bot (Firebase + modelo)
# --------------------------------------------------

def thread_bot():
    global db, modelo

    try:
        db = iniciar_firebase()
        print("✅ Firebase inicializado")
    except Exception as exc:
        print(f"⚠️ Firebase: {exc}")
        db = None

    try:
        modelo = modelo_inicial if modelo_inicial is not None else joblib.load(MODELO_PATH)
        print("✅ Modelo carregado")
    except Exception as exc:
        print(f"⚠️ Modelo: {exc}")
        modelo = None

    exchange = ccxt.kucoin()
    exchange.load_markets()
    moedas = [s for s in exchange.symbols if s.endswith("/USDT")]

    while True:
        atualizar_documentos_firestore()
        analisar_oportunidades(exchange, moedas)
        acompanhar_posicoes(exchange, carregar_posicoes())
        time.sleep(3600)

# --------------------------------------------------
# Arranque principal (Render exige app.run)
# --------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 A ouvir em 0.0.0.0:{port}")
    threading.Thread(
        target=app.run,
        kwargs=dict(host="0.0.0.0", port=port, debug=False, use_reloader=False),
        daemon=True
    ).start()

    threading.Thread(target=thread_bot, daemon=True).start()

    while True:
        time.sleep(86400)
