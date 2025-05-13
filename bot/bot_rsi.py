# bot/bot.py – mesmo comportamento, apenas ordem de arranque ajustada
# -----------------------------------------------------------------
# ✔ Mantém TODA a lógica original (funções, variáveis, imports pesados)
# ✔ Remove apenas os `exit()` e carrega Firebase + Modelo dentro da thread do bot
# ✔ Servidor Flask arranca primeiro, evitando o port‑scan timeout no Render
# -----------------------------------------------------------------

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
MODELO_PATH = "modelo/modelo_treinado.pkl"
db = None
modelo = None

# Constantes (inalteradas)
QUEDA_LIMITE = 0.95
OBJETIVO_PADRAO = 10
INTERVALO_RESUMO_HORAS = 2
MAX_ALERTAS_POR_CICLO = 5
ULTIMO_RESUMO = datetime.now() - pd.to_timedelta(INTERVALO_RESUMO_HORAS, unit="h")

# --------------------------------------------------
# Servidor Flask – arranca primeiro
# --------------------------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot RSI com modelo ativo."

@app.route("/treinar_modelo")
def treinar_modelo():
    global modelo
    try:
        from modelo.treino_modelo_firebase import atualizar_resultados_firestore, modelo as novo_modelo
        atualizar_resultados_firestore()
        modelo = novo_modelo
        return "✅ Modelo treinado com sucesso!"
    except Exception as e:
        return f"❌ Erro ao treinar modelo: {e}"

# --------------------------------------------------
# Utilitários
# --------------------------------------------------

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": mensagem})
    except Exception as e:
        print(f"❌ Erro ao enviar Telegram: {e}")

# --------------------------------------------------
# Funções de Firestore e bot (inalteradas excepto uso de globais)
# --------------------------------------------------

def guardar_previsao_firestore(registo):
    if db is None:
        return
    try:
        db.collection("historico_previsoes").add(registo)
    except Exception as e:
        print(f"❌ Erro ao guardar previsão no Firestore: {e}")


def guardar_estrategia_firestore(moeda, direcao, preco, sinais, rsi, variacao):
    if db is None:
        return
    estrategia = {
        "Moeda": moeda,
        "Direcao": direcao,
        "Preço": preco,
        "Sinais": sinais,
        "RSI": rsi,
        "Variação (%)": variacao,
        "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        db.collection("estrategias").add(estrategia)
    except Exception as e:
        print(f"❌ Erro ao guardar estratégia: {e}")


def carregar_posicoes():
    if db is None:
        return []
    return [doc.to_dict() for doc in db.collection("posicoes").stream()]


def guardar_posicoes(posicoes):
    if db is None:
        return
    for doc in db.collection("posicoes").stream():
        doc.reference.delete()
    for pos in posicoes:
        db.collection("posicoes").add(pos)


# --------------------------------------------------
# Análise e ciclo principal — mantém lógica original
# --------------------------------------------------

def analisar_oportunidades(exchange, moedas):
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

            entrada = pd.DataFrame([
                {
                    "RSI": rsi,
                    "EMA_diff": (preco - ema) / ema,
                    "MACD_diff": macd_val - macd_sig,
                    "Volume_relativo": (vol / vol_med) if vol_med else 1,
                    "BB_position": ((preco - bb_inf) / (bb_sup - bb_inf)) if bb_sup > bb_inf else 0.5,
                }
            ])

            prev = modelo.predict(entrada)[0] if modelo else 0

            registo = {
                "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Moeda": moeda,
                "RSI": rsi,
                "EMA_diff": entrada["EMA_diff"].iloc[0],
                "MACD_diff": entrada["MACD_diff"].iloc[0],
                "Volume_relativo": entrada["Volume_relativo"].iloc[0],
                "BB_position": entrada["BB_position"].iloc[0],
                "Previsao": int(prev),
                "resultado": None,
            }
            guardar_previsao_firestore(registo)

            if prev:
                sinais = [s for s in [
                    "RSI < 30" if rsi < 30 else None,
                    "preço>EMA" if preco > ema else None,
                    "MACD>sinal" if macd_val > macd_sig else None,
                    "volume alto" if vol > vol_med else None,
                    "fora da BB inf" if preco < bb_inf else None,
                ] if s]
                guardar_estrategia_firestore(moeda, "ENTRADA", preco, ", ".join(sinais), rsi, (preco - ema) / ema * 100)
                oportunidades.append({
                    "MACD_diff": registo["MACD_diff"],
                    "Mensagem": f"🚨 {moeda}: RSI={rsi:.2f}, EMA={ema:.2f}, MACD={macd_val:.2f}/{macd_sig:.2f}",
                })

        except Exception as e:
            print(f"⚠️ Erro analisar {moeda}: {e}")

    for msg in sorted(oportunidades, key=lambda x: -abs(x["MACD_diff"]))[:MAX_ALERTAS_POR_CICLO]:
        enviar_telegram(msg["Mensagem"])


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
            data = doc.to_dict()
            if "resultado" not in data:
                db.collection("historico_previsoes").document(doc.id).set({"resultado": None}, merge=True)
    except Exception as e:
        print(f"❌ Erro ao atualizar docs: {e}")


def iniciar_bot():
    global db, modelo

    # 🔸 Inicializar Firebase só aqui
    try:
        db = iniciar_firebase()
        print("✅ Firebase inicializado")
    except Exception as e:
        print(f"⚠️ Firebase: {
