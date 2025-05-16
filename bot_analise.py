"""
🔍 Bot de Análise de Oportunidades com Modelo Treinado Externamente

Este bot:
- Assume que o modelo já foi treinado por bot_treino.py (executado por cron job)
- Carrega o modelo de 'modelo_treinado.pkl'
- Atualiza resultados pendentes no Firestore
- Analisa TODAS as moedas USDT com indicadores técnicos
- Usa ML para prever oportunidades e envia alertas via Telegram
- Ignora moedas onde já existe posição aberta
"""

import os
import joblib
import ccxt
import pandas as pd
from datetime import datetime
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands

from firebase_config import iniciar_firebase
from telegram_alert import enviar_telegram

# Inicializa Firebase
db = iniciar_firebase()

# 🔁 Atualizar documentos pendentes com previsão
def atualizar_resultados_firestore(modelo):
    docs = db.collection("historico_previsoes").where("resultado", "==", "pendente").stream()
    total, atualizados = 0, 0

    for doc in docs:
        data = doc.to_dict()
        total += 1
        campos = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position"]
        if all(c in data for c in campos):
            entrada = pd.DataFrame([data])[campos]
            pred = modelo.predict(entrada)[0]
            db.document(doc.reference.path).update({"resultado": float(pred)})
            atualizados += 1

    print(f"📌 Atualizados {atualizados} de {total} resultados pendentes.")

# 📊 Carregar posições existentes
def carregar_posicoes():
    docs = db.collection("posicoes").stream()
    return [doc.to_dict() for doc in docs]

# 🔥 Guardar qualquer registo no Firestore
def guardar_firestore(colecao, dados):
    try:
        dados["timestamp"] = datetime.utcnow()
        db.collection(colecao).add(dados)
    except Exception as e:
        print(f"❌ Erro ao guardar em {colecao}: {e}")

# 🧠 Analisar oportunidades com modelo ML
def analisar_oportunidades(modelo):
    exchange = ccxt.kucoin()
    exchange.load_markets()
    symbols = [s for s in exchange.symbols if s.endswith("/USDT")]

    # Ignorar moedas já em posição
    moedas_em_posicao = {p['simbolo'] for p in carregar_posicoes() if 'simbolo' in p}

    oportunidades = []

    for simbolo in symbols:
        if simbolo in moedas_em_posicao:
            continue

        try:
            ohlcv = exchange.fetch_ohlcv(simbolo, timeframe="1h", limit=100)
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

            df["RSI"] = RSIIndicator(df["close"]).rsi()
            df["EMA"] = EMAIndicator(df["close"]).ema_indicator()
            df["EMA_diff"] = df["close"] - df["EMA"]
            macd = MACD(df["close"])
            df["MACD_diff"] = macd.macd_diff()
            bb = BollingerBands(df["close"])
            df["BB_position"] = (df["close"] - bb.bollinger_lband()) / (bb.bollinger_hband() - bb.bollinger_lband())

            df.dropna(inplace=True)
            entrada = df.iloc[-1][["RSI", "EMA_diff", "MACD_diff", "volume", "BB_position"]].rename({"volume": "Volume_relativo"})
            entrada = entrada.to_frame().T
            previsao = modelo.predict(entrada)[0]

            if previsao == 1:
                mensagem = f"🚀 ML Sinal de Entrada: {simbolo}\nRSI: {entrada['RSI'].values[0]:.2f}"
                enviar_telegram(mensagem)

                guardar_firestore("historico_previsoes", {
                    **entrada.to_dict(orient="records")[0],
                    "simbolo": simbolo,
                    "previsao": float(previsao),
                    "resultado": "pendente"
                })
                oportunidades.append(simbolo)

        except Exception as e:
            print(f"⚠️ Erro ao analisar {simbolo}: {e}")

    print(f"🔔 {len(oportunidades)} novas oportunidades identificadas com ML.")

# 🚀 Execução principal
def main():
    try:
        modelo = joblib.load("modelo_treinado.pkl")
    except Exception as e:
        print(f"❌ Erro ao carregar modelo_treinado.pkl: {e}")
        return

    atualizar_resultados_firestore(modelo)
    analisar_oportunidades(modelo)

if __name__ == "__main__":
    main()
