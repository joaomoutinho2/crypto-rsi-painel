import time
import ccxt
import pandas as pd
import requests
import os
import json
from flask import Flask
from datetime import datetime, timedelta
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands
from config import TIMEFRAME, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

FICHEIRO_POSICOES = "posicoes.json"
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

def analisar_oportunidades(exchange, moedas):
    oportunidades = []
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
            if vol > vol_med: sinais += 1

            if sinais >= 3:
                oportunidades.append({
                    "moeda": moeda,
                    "preco": preco,
                    "rsi": rsi,
                    "sinais": sinais,
                    "ema": ema,
                    "macd": macd,
                    "macd_sig": macd_sig,
                    "vol": vol,
                    "vol_med": vol_med,
                    "bb_inf": bb_inf,
                    "bb_sup": bb_sup
                })

        except Exception as e:
            print(f"⚠️ Erro em {moeda}:", e)

    top = sorted(oportunidades, key=lambda x: -x["sinais"])[:5]
    for o in top:
        mensagem = (
            f"🚨 Oportunidade: {o['moeda']}\n"
            f"💰 Preço: {o['preco']:.2f} USDT\n"
            f"📊 RSI: {o['rsi']:.2f} | EMA: {o['ema']:.2f}\n"
            f"📈 MACD: {o['macd']:.2f} / Sinal: {o['macd_sig']:.2f}\n"
            f"📉 Volume: {o['vol']:.2f} (média: {o['vol_med']:.2f})\n"
            f"🎯 Bollinger: [{o['bb_inf']:.2f} ~ {o['bb_sup']:.2f}]\n"
            f"⚙️ Força: {o['sinais']}/5"
        )
        enviar_telegram(mensagem)

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
                enviar_telegram(
                    f"🔁 {moeda}: Preço caiu. Considerar reforço?\n"
                    f"Atual: {preco_atual:.2f} | Entrada: {preco_entrada:.2f}"
                )
            elif percent >= objetivo:
                enviar_telegram(
                    f"🎯 {moeda}: Objetivo de lucro atingido ({percent:.2f}%)!\n"
                    f"Atual: {preco_atual:.2f} | Entrada: {preco_entrada:.2f}"
                )

            linhas.append(f"{moeda} | Entrada: {preco_entrada:.2f} | Atual: {preco_atual:.2f} | Lucro: {lucro:.2f}€ ({percent:.2f}%)")

        except Exception as e:
            print(f"Erro em {pos['moeda']}:", e)

    if forcar_resumo or (agora - ULTIMO_RESUMO).total_seconds() > INTERVALO_RESUMO_HORAS * 3600:
        if linhas:
            resumo = "📌 Resumo das tuas posições:\n\n" + "\n".join(f"{i+1}. {linha}" for i, linha in enumerate(linhas))
            resumo += f"\n\n⌛ Atualizado: {agora.strftime('%H:%M')}"
            enviar_telegram(resumo)
            ULTIMO_RESUMO = agora

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
