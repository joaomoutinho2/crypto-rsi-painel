
import time
import ccxt
import pandas as pd
import requests
import os
import json
from datetime import datetime
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands
from flask import Flask
import threading
from config import TIMEFRAME, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

FICHEIRO_POSICOES = "posicoes.json"

# 📤 Enviar alerta para o Telegram
def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
    try:
        response = requests.post(url, data=data)
        if response.status_code != 200:
            print("❌ Erro Telegram:", response.text)
    except Exception as e:
        print("❌ Exceção Telegram:", e)

# 📁 Carregar posições registadas
def carregar_posicoes():
    if not os.path.exists(FICHEIRO_POSICOES):
        return []
    with open(FICHEIRO_POSICOES, "r") as f:
        return json.load(f)

# 🔍 Análise de oportunidades
def analisar_oportunidades(exchange, moedas, limite=5):
    oportunidades = []
    for moeda in moedas:
        try:
            candles = exchange.fetch_ohlcv(moeda, timeframe=TIMEFRAME, limit=100)
            df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["RSI"] = RSIIndicator(close=df["close"]).rsi()
            df["EMA"] = EMAIndicator(close=df["close"]).ema_indicator()
            df["MACD"] = MACD(close=df["close"]).macd()
            df["MACD_signal"] = MACD(close=df["close"]).macd_signal()
            bb = BollingerBands(close=df["close"])
            df["BB_lower"] = bb.bollinger_lband()
            df["BB_upper"] = bb.bollinger_hband()

            rsi = df["RSI"].iloc[-1]
            preco = df["close"].iloc[-1]
            ema = df["EMA"].iloc[-1]
            macd = df["MACD"].iloc[-1]
            macd_sig = df["MACD_signal"].iloc[-1]
            bb_inf = df["BB_lower"].iloc[-1]
            bb_sup = df["BB_upper"].iloc[-1]

            sinais = 0
            if rsi < 30: sinais += 1
            if preco < bb_inf: sinais += 1
            if preco > ema: sinais += 1
            if macd > macd_sig: sinais += 1

            if sinais >= 3:
                oportunidades.append((moeda, preco, rsi, sinais))
        except:
            continue

    oportunidades.sort(key=lambda x: -x[3])
    return oportunidades[:limite]

# 🔄 Verificar posições registadas
def acompanhar_posicoes(exchange, posicoes):
    for pos in posicoes:
        try:
            ticker = exchange.fetch_ticker(pos["moeda"])
            preco_atual = ticker["last"]
            preco_entrada = pos["preco_entrada"]
            investido = pos["montante"]
            objetivo = pos.get("objetivo", 10)

            valor_atual = preco_atual * (investido / preco_entrada)
            lucro = valor_atual - investido
            percent = (lucro / investido) * 100

            if preco_atual < preco_entrada * 0.95:
                enviar_telegram(
                    f"🔁 {pos['moeda']}: Preço caiu. Considerar reforço?\n"
                    f"Atual: {preco_atual:.2f} | Entrada: {preco_entrada:.2f}"
                )
            elif percent >= objetivo:
                enviar_telegram(f"🎯 {pos['moeda']}: Objetivo de lucro atingido ({percent:.2f}%)!
Atual: {preco_atual:.2f} | Entrada: {preco_entrada:.2f}")
        except:
            continue

# 🔁 Ciclo principal
def iniciar_bot():
    exchange = ccxt.kucoin()
    exchange.load_markets()
    moedas = [s for s in exchange.symbols if "/USDT" in s and "UP/" not in s and "DOWN/" not in s]

    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Verificando mercado...")
        oportunidades = analisar_oportunidades(exchange, moedas)
        for moeda, preco, rsi, sinais in oportunidades:
            enviar_telegram(f"🚨 Oportunidade: {moeda}
💰 Preço: {preco:.2f} | RSI: {rsi:.2f} | Força: {sinais}/4")

        posicoes = carregar_posicoes()
        acompanhar_posicoes(exchange, posicoes)

        print("⏱️ A aguardar 1 hora...")
        time.sleep(3600)

# 🌐 Servidor Flask (Render)
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot RSI filtrado a correr no Render."

# ▶️ Iniciar bot e webserver
if __name__ == "__main__":
    threading.Thread(target=iniciar_bot).start()
    app.run(host="0.0.0.0", port=10000)

