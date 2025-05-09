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
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

# Lê a variável de ambiente como string
firebase_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
firebase_dict = json.loads(firebase_json)

# Inicializa o Firebase com o dicionário
cred = credentials.Certificate(firebase_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

firebase_admin.initialize_app(cred)
db = firestore.client()


FICHEIRO_POSICOES = "posicoes.json"
MODELO_PATH = "modelo_treinado.pkl"
FICHEIRO_PREVISOES = "historico_previsoes.csv"
QUEDA_LIMITE = 0.95
OBJETIVO_PADRAO = 10
INTERVALO_RESUMO_HORAS = 2
MAX_ALERTAS_POR_CICLO = 5  # Limite de alertas por ciclo

ULTIMO_RESUMO = datetime.now() - timedelta(hours=2)

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

def gravar_previsao(registo):
    df = pd.DataFrame([registo])
    existe = os.path.exists(FICHEIRO_PREVISOES)
    df.to_csv(FICHEIRO_PREVISOES, mode="a", header=not existe, index=False)

def guardar_posicoes(posicoes):
    # Apagar todas as posições antigas
    for doc in db.collection("posicoes").stream():
        doc.reference.delete()
    # Adicionar as novas
    for pos in posicoes:
        db.collection("posicoes").add(pos)

def carregar_posicoes():
    docs = db.collection("posicoes").stream()
    return [doc.to_dict() for doc in docs]


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

            previsao = modelo.predict(entrada)[0]

            registo = {
                "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Moeda": moeda,
                "RSI": rsi,
                "EMA_diff": entrada["EMA_diff"].iloc[0],
                "MACD_diff": entrada["MACD_diff"].iloc[0],
                "Volume_relativo": entrada["Volume_relativo"].iloc[0],
                "BB_position": entrada["BB_position"].iloc[0],
                "Previsao": int(previsao)
            }

            gravar_previsao(registo)

            if previsao:
                registo["Mensagem"] = (
                    f"🚨 Oportunidade: {moeda}\n"
                    f"💰 Preço: {preco:.2f} USDT\n"
                    f"📊 RSI: {rsi:.2f} | EMA: {ema:.2f}\n"
                    f"📈 MACD: {macd_val:.2f} / Sinal: {macd_sig:.2f}\n"
                    f"📉 Volume: {vol:.2f} (média: {vol_med:.2f})\n"
                    f"🎯 Bollinger: [{bb_inf:.2f} ~ {bb_sup:.2f}]\n"
                    f"⚙️ Entrada considerada promissora ✅"
                )
                oportunidades.append(registo)

        except Exception as e:
            print(f"⚠️ Erro em {moeda}:", e)

    # Ordenar oportunidades por maior força (soma de indicadores positivos)
    oportunidades_ordenadas = sorted(oportunidades, key=lambda x: (
        -abs(x["MACD_diff"]),
        -abs(x["EMA_diff"]),
        -abs(x["Volume_relativo"]),
        -abs(0.5 - x["BB_position"]),  # mais perto das extremidades é melhor
        x["RSI"]
    ))

    for registo in oportunidades_ordenadas[:MAX_ALERTAS_POR_CICLO]:
        enviar_telegram(registo["Mensagem"])

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
                enviar_telegram(f"🔁 {moeda}: Preço caiu. Considerar reforço? Atual: {preco_atual:.2f} | Entrada: {preco_entrada:.2f}")
            elif percent >= objetivo:
                enviar_telegram(f"🎯 {moeda}: Objetivo de lucro atingido ({percent:.2f}%)! Atual: {preco_atual:.2f} | Entrada: {preco_entrada:.2f}")

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
    print("🔁 Iniciando bot com modelo (limitado)...")
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
    return "✅ Bot RSI com modelo, previsões e limite de alertas ativo."

if __name__ == "__main__":
    threading.Thread(target=iniciar_bot).start()
    app.run(host="0.0.0.0", port=10000)

# Carregar posições existentes
posicoes = carregar_posicoes()

# Formulário para registrar uma nova posição
st.title("💼 Registrar Nova Posição")
with st.form("form_nova_posicao"):
    moeda = st.text_input("Moeda (ex: BTC/USDT)")
    montante = st.number_input("Montante investido (€)", min_value=0.0, step=0.01)
    preco_entrada = st.number_input("Preço de entrada (USDT)", min_value=0.0, step=0.01)
    objetivo = st.number_input("Objetivo de lucro (%)", min_value=0.0, step=0.1, value=10.0)
    submeter = st.form_submit_button("Registrar Posição")

    if submeter:
        # Validar os dados antes de salvar
        if not moeda or montante <= 0 or preco_entrada <= 0:
            st.error("❌ Todos os campos devem ser preenchidos corretamente.")
        else:
            # Criar nova posição
            nova_posicao = {
                "moeda": moeda,
                "montante": montante,
                "preco_entrada": preco_entrada,
                "objetivo": objetivo,
                "data": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            # Adicionar nova posição à lista
            posicoes.append(nova_posicao)
            # Salvar no arquivo JSON
            guardar_posicoes(posicoes)
            st.success("✅ Posição registrada com sucesso!")
            st.rerun()  # Atualizar a página
