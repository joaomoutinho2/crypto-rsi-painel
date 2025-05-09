
import time
import ccxt
import pandas as pd
import requests
import os
import json
import joblib
import threading
from flask import Flask
from datetime import datetime, timedelta
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands
from config import TIMEFRAME, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

FICHEIRO_POSICOES = "posicoes.json"
MODELO_PATH = "modelo_treinado.pkl"
QUEDA_LIMITE = 0.95
OBJETIVO_PADRAO = 10
ULTIMO_RESUMO = datetime.now() - timedelta(hours=2)
INTERVALO_RESUMO_HORAS = 2

def enviar_telegram(mensagem):
    print("📤 Enviar para Telegram:")
    print(mensagem)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
    try:
        response = requests.post(url, data=data)
        print("🔁 Código:", response.status_code)
    except Exception as e:
        print("❌ Erro ao enviar:", e)

def carregar_posicoes():
    if not os.path.exists(FICHEIRO_POSICOES):
        return []
    try:
        with open(FICHEIRO_POSICOES, "r") as f:
            return json.load(f)
    except:
        return []

def analisar_oportunidades(exchange, moedas, modelo):
    oportunidades = []
    for moeda in moedas:
        try:
            candles = exchange.fetch_ohlcv(moeda, timeframe=TIMEFRAME, limit=100)
            df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["RSI"] = RSIIndicator(close=df["close"]).rsi()
            df["EMA"] = EMAIndicator(close=df["close"]).ema_indicator()
            macd = MACD(close=df["close"])
            df["MACD"] = macd.macd()
            df["MACD_signal"] = macd.macd_signal()
            df["volume_medio"] = df["volume"].rolling(window=14).mean()
            bb = BollingerBands(close=df["close"])
            df["BB_lower"] = bb.bollinger_lband()
            df["BB_upper"] = bb.bollinger_hband()

            rsi = df["RSI"].iloc[-1]
            preco = df["close"].iloc[-1]
            ema = df["EMA"].iloc[-1]
            macd_val = df["MACD"].iloc[-1]
            macd_sig = df["MACD_signal"].iloc[-1]
            vol = df["volume"].iloc[-1]
            vol_med = df["volume_medio"].iloc[-1]
            bb_inf = df["BB_lower"].iloc[-1]
            bb_sup = df["BB_upper"].iloc[-1]

            entrada = pd.DataFrame([{
                "RSI": rsi,
                "EMA_diff": (preco - ema) / ema,
                "MACD_diff": macd_val - macd_sig,
                "Volume_relativo": vol / vol_med if vol_med else 1,
                "BB_position": (preco - bb_inf) / (bb_sup - bb_inf) if bb_sup > bb_inf else 0.5
            }])

            if modelo.predict(entrada)[0]:
                mensagem = (
                    f"🚨 Oportunidade: {moeda}"
                    f"💰 Preço: {preco:.2f} USDT"
                    f"📊 RSI: {rsi:.2f} | EMA: {ema:.2f}"
                    f"📈 MACD: {macd_val:.2f} / Sinal: {macd_sig:.2f}"
                    f"📉 Volume: {vol:.2f} (média: {vol_med:.2f})"
                    f"🎯 Bollinger: [{bb_inf:.2f} ~ {bb_sup:.2f}]"
                    f"⚙️ Entrada considerada promissora ✅"
                )
                enviar_telegram(mensagem)

        except Exception as e:
            print(f"⚠️ Erro em {moeda}:", e)

def acompanhar_posicoes(exchange, posicoes, forcar_resumo=False):
    global ULTIMO_RESUMO
    linhas = []
    agora = datetime.now()

    for pos in posicoes:
        try:
            moeda = pos["moeda"]
            ticker = exchange.fetch_ticker(moeda)
            preco_atual = ticker["last"]
            preco_entrada = pos["preco_entrada"]
            investido = pos["montante"]
            objetivo = pos.get("objetivo", OBJETIVO_PADRAO)
            valor_atual = preco_atual * (investido / preco_entrada)
            lucro = valor_atual - investido
            percent = (lucro / investido) * 100

            if preco_atual < preco_entrada * QUEDA_LIMITE:
                enviar_telegram(f"🔁 {moeda}: Preço caiu. Considerar reforço?
Atual: {preco_atual:.2f} | Entrada: {preco_entrada:.2f}")
            elif percent >= objetivo:
                enviar_telegram(f"🎯 {moeda}: Objetivo de lucro atingido ({percent:.2f}%)!
Atual: {preco_atual:.2f} | Entrada: {preco_entrada:.2f}")

            linhas.append(f"{moeda} | Entrada: {preco_entrada:.2f} | Atual: {preco_atual:.2f} | Lucro: {lucro:.2f}€ ({percent:.2f}%)")
        except Exception as e:
            print(f"Erro em {pos['moeda']}:", e)

    if forcar_resumo or (agora - ULTIMO_RESUMO).total_seconds() > INTERVALO_RESUMO_HORAS * 3600:
        if linhas:
            resumo = "📌 Resumo das tuas posições:" + "\n".join(f"{i+1}. {linha}" for i, linha in enumerate(linhas))
            resumo += f"\n\n⌛ Atualizado: {agora.strftime('%H:%M')}"
            enviar_telegram(resumo)
            ULTIMO_RESUMO = agora

def iniciar_bot():
    print("🔁 Iniciando bot com modelo...")
    modelo = joblib.load(MODELO_PATH)
    exchange = ccxt.kucoin()
    exchange.load_markets()
    moedas = [s for s in exchange.symbols if "/USDT" in s and "UP/" not in s and "DOWN/" not in s]

    while True:
        print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Ciclo iniciado.")
        analisar_oportunidades(exchange, moedas, modelo)
        acompanhar_posicoes(exchange, carregar_posicoes())
        print("⏸️ Esperar 1 hora...\n")
        time.sleep(3600)

app = Flask(__name__)
@app.route('/')
def home():
    return "✅ Bot RSI com modelo e debug está ativo."

if __name__ == "__main__":
    threading.Thread(target=iniciar_bot).start()
    app.run(host="0.0.0.0", port=10000)
