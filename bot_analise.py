"""
🔍 Bot de Análise de Oportunidades de Investimento em Criptomoedas

Este bot analisa moedas USDT no KuCoin, calcula indicadores técnicos, regista oportunidades de entrada e acompanha posições em aberto.
Envia alertas via Telegram e atualiza o Firestore com os resultados.
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

# 🔁 Carregar modelo
MODELO_PATH = "modelo_treinado.pkl"
modelo = joblib.load(MODELO_PATH)

# 📊 Função para carregar posições atuais do Firestore
def carregar_posicoes():
    docs = db.collection("posicoes").stream()
    return [doc.to_dict() for doc in docs]

# 🔥 Guardar previsão ou estratégia

def guardar_firestore(colecao, dados):
    try:
        dados["timestamp"] = datetime.utcnow()
        db.collection(colecao).add(dados)
    except Exception as e:
        print(f"❌ Erro ao guardar em {colecao}: {e}")

# 🔁 Atualizar documentos pendentes com previsão

def atualizar_documentos_firestore():
    docs = db.collection("historico_previsoes").where("resultado", "==", "pendente").stream()
    atualizados = 0
    for doc in docs:
        dados = doc.to_dict()
        if all(c in dados for c in ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position"]):
            entrada = pd.DataFrame([dados])
            previsao = modelo.predict(entrada)[0]
            db.document(doc.reference.path).update({"resultado": float(previsao)})
            atualizados += 1
    print(f"🛠️ {atualizados} documentos atualizados com 'resultado'.")

# 💸 Atualizar preços de entrada

def atualizar_precos_de_entrada():
    posicoes = db.collection("posicoes").stream()
    exchange = ccxt.kucoin()
    for doc in posicoes:
        dados = doc.to_dict()
        if "preco_entrada" not in dados:
            simbolo = dados["simbolo"]
            ticker = exchange.fetch_ticker(simbolo)
            preco = ticker["last"]
            db.document(doc.reference.path).update({"preco_entrada": preco})

# 🧠 Analisar novas oportunidades

def analisar_oportunidades():
    exchange = ccxt.kucoin()
    exchange.load_markets()
    symbols = [s for s in exchange.symbols if s.endswith("/USDT")][:200]
    oportunidades = []

    for simbolo in symbols:
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
                mensagem = f"🚀 Oportunidade: {simbolo}\nRSI: {entrada['RSI'].values[0]:.2f}"
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

    print(f"🔔 {len(oportunidades)} oportunidades identificadas.")

# 📈 Acompanhar posições abertas e sugerir saída se objetivo atingido

def acompanhar_posicoes():
    posicoes = carregar_posicoes()
    exchange = ccxt.kucoin()
    for pos in posicoes:
        try:
            simbolo = pos["simbolo"]
            preco_entrada = pos["preco_entrada"]
            objetivo = pos.get("objetivo", 10)
            ticker = exchange.fetch_ticker(simbolo)
            preco_atual = ticker["last"]
            lucro = ((preco_atual - preco_entrada) / preco_entrada) * 100

            if lucro >= objetivo:
                mensagem = f"💰 Recomendado vender {simbolo}\nLucro: {lucro:.2f}%"
                enviar_telegram(mensagem)
        except Exception as e:
            print(f"❌ Erro ao acompanhar {simbolo}: {e}")

# 🚀 Função principal

def main():
    print("\n🚀 Iniciando ciclo de análise...")
    atualizar_documentos_firestore()
    analisar_oportunidades()
    acompanhar_posicoes()
    atualizar_precos_de_entrada()

if __name__ == "__main__":
    main()
