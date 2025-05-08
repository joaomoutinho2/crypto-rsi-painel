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
QUEDA_LIMITE = 0.95
OBJETIVO_PADRAO = 10
estado_alertas = {}

def enviar_telegram(mensagem):
    print("📤 Enviar para Telegram:")
    print(mensagem)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
    try:
        response = requests.post(url, data=data)
        print("🔁 Código:", response.status_code)
        print("📨 Resposta:", response.text)
        if response.status_code != 200:
            print("❌ Erro ao enviar para Telegram.")
    except Exception as e:
        print("❌ Exceção ao enviar:", e)

def carregar_posicoes():
    if not os.path.exists(FICHEIRO_POSICOES):
        return []
    try:
        with open(FICHEIRO_POSICOES, "r") as f:
            return json.load(f)
    except:
        return []

def analisar_oportunidades(exchange, moedas):
    for moeda in moedas:
        try:
            candles = exchange.fetch_ohlcv(moeda, timeframe=TIMEFRAME, limit=100)
            df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["RSI"] = RSIIndicator(close=df["close"]).rsi()
            df["EMA"] = EMAIndicator(close=df["close"]).ema_indicator()
            df["MACD"] = MACD(close=df["close"]).macd()
            df["MACD_signal"] = MACD(close=df["close"]).macd_signal()
            df["volume_medio"] = df["volume"].rolling(window=14).mean()
            bb = BollingerBands(close=df["close"])
            df["BB_lower"] = bb.bollinger_lband()
            df["BB_upper"] = bb.bollinger_hband()

            rsi = df["RSI"].iloc[-1]
            preco = df["close"].iloc[-1]
            ema = df["EMA"].iloc[-1]
            macd = df["MACD"].iloc[-1]
            macd_sig = df["MACD_signal"].iloc[-1]
            vol = df["volume"].iloc[-1]
            vol_med = df["volume_medio"].iloc[-1]
            bb_inf = df["BB_lower"].iloc[-1]
            bb_sup = df["BB_upper"].iloc[-1]

            sinais = 0
            if rsi < 30: sinais += 1
            if preco < bb_inf: sinais += 1
            if preco > ema: sinais += 1
            if macd > macd_sig: sinais += 1

            hash_alerta = f"{moeda}-{round(rsi, 1)}-{sinais}"
            if sinais >= 3 and estado_alertas.get(moeda) != hash_alerta:
                estado_alertas[moeda] = hash_alerta
                mensagem = (
                    f"🚨 Oportunidade: {moeda}\n"
                    f"💰 Preço: {preco:.2f} USDT\n"
                    f"📊 RSI: {rsi:.2f} | EMA: {ema:.2f}\n"
                    f"📈 MACD: {macd:.2f} / Sinal: {macd_sig:.2f}\n"
                    f"📉 Volume: {vol:.2f} (média: {vol_med:.2f})\n"
                    f"🎯 Bollinger: [{bb_inf:.2f} ~ {bb_sup:.2f}]\n"
                    f"⚙️ Força: {sinais}/4"
                )
                enviar_telegram(mensagem)
        except Exception as e:
            print(f"⚠️ Erro em {moeda}:", e)

def acompanhar_posicoes(exchange, posicoes):
    for pos in posicoes:
        try:
            ticker = exchange.fetch_ticker(pos["moeda"])
            preco_atual = ticker["last"]
            preco_entrada = pos["preco_entrada"]
            investido = pos["montante"]
            objetivo = pos.get("objetivo", OBJETIVO_PADRAO)

            valor_atual = preco_atual * (investido / preco_entrada)
            lucro = valor_atual - investido
            percent = (lucro / investido) * 100

            if preco_atual < preco_entrada * QUEDA_LIMITE:
                enviar_telegram(
                    f"🔁 {pos['moeda']}: Preço caiu. Considerar reforço?\n"
                    f"Atual: {preco_atual:.2f} | Entrada: {preco_entrada:.2f}"
                )
            elif percent >= objetivo:
                enviar_telegram(
                    f"🎯 {pos['moeda']}: Objetivo de lucro atingido ({percent:.2f}%)!\n"
                    f"Atual: {preco_atual:.2f} | Entrada: {preco_entrada:.2f}"
                )
        except Exception as e:
            print("⚠️ Erro posição:", e)

def iniciar_bot():
    exchange = ccxt.kucoin()
    try:
        exchange.load_markets()
    except Exception as e:
        print("❌ Erro a carregar mercados:", e)
        return

    moedas = [s for s in exchange.symbols if "/USDT" in s and "UP/" not in s and "DOWN/" not in s]

    while True:
        print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Ciclo iniciado.")
        analisar_oportunidades(exchange, moedas)
        acompanhar_posicoes(exchange, carregar_posicoes())
        print("⏸️ Esperar 1 hora...\n")
        time.sleep(3600)

# Flask app para manter ativo no Render
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot RSI com debug está ativo."

if __name__ == "__main__":
    threading.Thread(target=iniciar_bot).start()
    app.run(host="0.0.0.0", port=10000)
