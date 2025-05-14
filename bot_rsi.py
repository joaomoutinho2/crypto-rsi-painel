# bot_rsi.py — versão compatível com Render
# --------------------------------------------------
# ✔ Imports sensíveis movidos para dentro da thread
# ✔ app.run() corre no processo principal
# ✔ Firebase e modelo carregam só após o Flask subir
# --------------------------------------------------

import os
import time
import threading
from datetime import datetime, timedelta

import ccxt
import pandas as pd
import joblib
import requests
from flask import Flask
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands
from config import TIMEFRAME


# 🔹 Constantes simples e globais
db = None
modelo = None
MODELO_PATH = "modelo_treinado.pkl"

QUEDA_LIMITE = 0.95
OBJETIVO_PADRAO = 10
INTERVALO_RESUMO_HORAS = 2
MAX_ALERTAS_POR_CICLO = 5
ULTIMO_RESUMO = datetime.now() - pd.to_timedelta(INTERVALO_RESUMO_HORAS, unit="h")
OBJETIVO_LUCRO = 0.02       # 2%
LIMITE_PERDA = 0.02         # 2%
ULTIMO_TREINO = datetime.now() - timedelta(days=2)  # simula treino feito há 2 dias
INTERVALO_TREINO_DIAS = 1  # treina a cada 1 dia


# --------------------------------------------------
# Flask App
# --------------------------------------------------

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot RSI ativo."

@app.route("/treinar_modelo")
def treinar_modelo():
    global modelo
    try:
        from treino_modelo_firebase import atualizar_resultados_firestore, modelo as novo
        atualizar_resultados_firestore()
        modelo = novo
        return "✅ Modelo treinado com sucesso!"
    except Exception as e:
        return f"❌ Erro ao treinar modelo: {e}"

# --------------------------------------------------
# Telegram
# --------------------------------------------------

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def enviar_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Telegram não configurado –", mensagem)
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": mensagem})
    except Exception as e:
        print(f"❌ Telegram: {e}")

# --------------------------------------------------
# Firestore helpers
# --------------------------------------------------

from datetime import datetime, timedelta
import time

def atualizar_precos_de_entrada(exchange, timeframe="1h"):
    """
    Atualiza todos os documentos sem 'preco_entrada' com base no candle mais próximo da data da previsão.
    """
    print("🛠️ Atualizando documentos antigos com campo 'preco_entrada'...")

    try:
        docs = db.collection("historico_previsoes").stream()
        atualizados = 0
        total = 0

        for doc in docs:
            data = doc.to_dict()
            ref = doc.reference
            total += 1

            if "preco_entrada" in data:
                continue

            moeda = data.get("Moeda")
            data_str = data.get("Data")

            try:
                if not moeda or not data_str:
                    continue

                dt = datetime.strptime(data_str, "%Y-%m-%d %H:%M:%S")
                timestamp = int(time.mktime((dt - timedelta(minutes=5)).timetuple())) * 1000  # começa 5min antes

                candles = exchange.fetch_ohlcv(moeda, timeframe=timeframe, since=timestamp, limit=5)
                if not candles:
                    print(f"⚠️ Sem candles para {moeda} em {data_str}")
                    continue

                # Encontrar o candle mais próximo
                candle_proximo = min(candles, key=lambda x: abs(x[0] - int(dt.timestamp() * 1000)))
                preco_close = candle_proximo[4]

                ref.set({"preco_entrada": preco_close}, merge=True)
                print(f"✅ {moeda} @ {data_str} → {preco_close:.4f}")
                atualizados += 1

            except Exception as e:
                print(f"⚠️ Erro em {moeda} @ {data_str}: {e}")

        print(f"\n📊 {atualizados}/{total} documentos atualizados com 'preco_entrada'.")

    except Exception as e:
        print(f"❌ Erro ao atualizar preços de entrada: {e}")

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
    try:
        return [doc.to_dict() for doc in db.collection("posicoes").stream()]
    except Exception as e:
        print(f"❌ Erro carregar posições: {e}")
        return []

# --------------------------------------------------
# Bot logic
# --------------------------------------------------

def analisar_oportunidades(exchange, moedas):
    print("🧪 [DEBUG] analisar_oportunidades começou...")
    oportunidades = []

    for moeda in moedas[:3]:  # testamos só 3 para ser mais rápido
        print(f"🧪 [DEBUG] Analisando {moeda}")
        try:
            ...
            print(f"🧪 [DEBUG] Prev: {prev}")

            # FORÇA ALERTA
            enviar_telegram(f"🔔 Alerta forçado para {moeda}")
        except Exception as exc:
            print(f"⚠️ Erro ao analisar {moeda}: {exc}")


def avaliar_resultados(exchange):
    """
    Atualiza documentos com resultado 'pendente' ou None para 0 (perda) ou 1 (ganho)
    com base no preço atual da moeda.
    """
    print("📈 A avaliar previsões pendentes...")

    try:
        docs = db.collection("historico_previsoes").where("resultado", "in", ["pendente", None]).stream()
        atualizados = 0
        total = 0

        for doc in docs:
            total += 1
            data = doc.to_dict()
            ref = doc.reference

            try:
                moeda = data["Moeda"]
                preco_entrada = float(data.get("preco_entrada") or 0)
                if preco_entrada == 0:
                    print(f"⚠️ Ignorado {moeda}: preço de entrada inválido.")
                    continue

                ticker = exchange.fetch_ticker(moeda)
                preco_atual = ticker["last"]

                variacao = (preco_atual - preco_entrada) / preco_entrada

                if variacao >= OBJETIVO_LUCRO:
                    resultado = 1  # ganho
                elif variacao <= -LIMITE_PERDA:
                    resultado = 0  # perda
                else:
                    continue  # ainda pendente

                ref.set({"resultado": resultado}, merge=True)
                print(f"✅ {moeda}: resultado atualizado para {resultado}")
                atualizados += 1

            except Exception as e:
                print(f"⚠️ Erro ao processar {data.get('Moeda')}: {e}")

        print(f"\n📊 {atualizados}/{total} previsões pendentes atualizadas.")

    except Exception as e:
        print(f"❌ Erro ao avaliar previsões: {e}")



def acompanhar_posicoes(exchange, posicoes):
    global ULTIMO_RESUMO
    agora = datetime.now()
    linhas = []

    for pos in posicoes:
        try:
            ticker = exchange.fetch_ticker(pos["moeda"])
            preco_atual = ticker["last"]
            preco_entrada = pos["preco_entrada"]
            montante = pos["montante"]

            valor_atual = preco_atual * (montante / preco_entrada)
            lucro = valor_atual - montante
            percent = (lucro / montante) * 100

            linhas.append(
                f"{pos['moeda']}: {percent:+.2f}% | Entrada: {preco_entrada:.4f} | Atual: {preco_atual:.4f} | Lucro: {lucro:+.2f} USDT"
            )

        except Exception as e:
            print(f"⚠️ Erro ao acompanhar {pos['moeda']}: {e}")

    if (agora - ULTIMO_RESUMO).total_seconds() > INTERVALO_RESUMO_HORAS * 3600:
        if linhas:
            mensagem = "📈 Atualização de posições:\n" + "\n".join(linhas)
            enviar_telegram(mensagem)
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
# Thread principal do bot
# --------------------------------------------------

def thread_bot():
    global db, modelo
    try:
        from firebase_config import iniciar_firebase
        from treino_modelo_firebase import modelo as modelo_inicial

        db = iniciar_firebase()
        print("✅ Firebase inicializado")

        modelo = modelo_inicial if modelo_inicial is not None else joblib.load(MODELO_PATH)
        print("✅ Modelo carregado")

        exchange = ccxt.kucoin()
        exchange.load_markets()
        moedas = [s for s in exchange.symbols if s.endswith("/USDT")]

        while True:
            # Verificar se está na hora de treinar novamente
            global ULTIMO_TREINO
            agora = datetime.now()
            if (agora - ULTIMO_TREINO).days >= INTERVALO_TREINO_DIAS:
                try:
                    from treino_modelo_firebase import treinar_modelo_automaticamente
                    treinar_modelo_automaticamente()
                    ULTIMO_TREINO = agora
                except Exception as e:
                    print(f"⚠️ Erro ao treinar automaticamente: {e}")
            atualizar_precos_de_entrada(exchange)
            atualizar_documentos_firestore()
            analisar_oportunidades(exchange, moedas)
            avaliar_resultados(exchange)
            acompanhar_posicoes(exchange, carregar_posicoes())
            time.sleep(3600)

    except Exception as exc:
        print(f"❌ Erro na thread do bot: {exc}")

# --------------------------------------------------
# Arranque principal — obrigatoriamente com app.run
# --------------------------------------------------

if __name__ == "__main__":
    threading.Thread(target=thread_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 A ouvir em 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
