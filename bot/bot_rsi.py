import os
import time
import threading
import ccxt
import pandas as pd
import joblib
import requests
from flask import Flask
from datetime import datetime
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands

from utils.config import TIMEFRAME, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from utils.firebase_config import iniciar_firebase
from modelo.treino_modelo_firebase import modelo

# ✅ Inicializar Firestore
try:
    db = iniciar_firebase()
except Exception as e:
    print(f"❌ Erro ao inicializar o Firestore: {e}")
    exit()

# ✅ Verificar se o modelo foi carregado com sucesso
if modelo is None:
    print("❌ Erro ao treinar ou carregar o modelo. A sair...")
    exit()

# Constantes
MODELO_PATH = "modelo/modelo_treinado.pkl"
QUEDA_LIMITE = 0.95
OBJETIVO_PADRAO = 10
INTERVALO_RESUMO_HORAS = 2
MAX_ALERTAS_POR_CICLO = 5
ULTIMO_RESUMO = datetime.now() - pd.to_timedelta(INTERVALO_RESUMO_HORAS, unit='h')

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot RSI com modelo ativo."

@app.route('/treinar_modelo')
def treinar_modelo():
    try:
        from modelo.treino_modelo_firebase import atualizar_resultados_firestore
        atualizar_resultados_firestore()
        return "✅ Modelo treinado com sucesso!"
    except Exception as e:
        return f"❌ Erro ao treinar modelo: {e}"


def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"❌ Erro ao enviar Telegram: {e}")


def guardar_previsao_firestore(registo):
    try:
        campos_necessarios = ["Data", "Moeda", "RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position", "Previsao", "resultado"]
        faltam = [campo for campo in campos_necessarios if campo not in registo]
        if faltam:
            print(f"❌ Não foi possível guardar o registo. Faltam campos: {faltam}")
            return
        db.collection("historico_previsoes").add(registo)
    except Exception as e:
        print(f"❌ Erro ao guardar previsão no Firestore: {e}")


def guardar_estrategia_firestore(moeda, direcao, preco, sinais, rsi, variacao):
    estrategia = {
        "Moeda": moeda,
        "Direcao": direcao,
        "Preço": preco,
        "Sinais": sinais,
        "RSI": rsi,
        "Variação (%)": variacao,
        "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        db.collection("estrategias").add(estrategia)
    except Exception as e:
        print(f"❌ Erro ao guardar estratégia: {e}")


def carregar_posicoes():
    return [doc.to_dict() for doc in db.collection("posicoes").stream()]


def guardar_posicoes(posicoes):
    for doc in db.collection("posicoes").stream():
        doc.reference.delete()
    for pos in posicoes:
        db.collection("posicoes").add(pos)


def analisar_oportunidades(exchange, moedas, modelo):
    oportunidades = []
    for moeda in moedas:
        try:
            candles = exchange.fetch_ohlcv(moeda, timeframe=TIMEFRAME, limit=100)
            df = pd.DataFrame(candles, columns=["timestamp","open","high","low","close","volume"])
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
                "EMA_diff": (preco-ema)/ema,
                "MACD_diff": macd_val-macd_sig,
                "Volume_relativo": (vol/vol_med) if vol_med else 1,
                "BB_position": ((preco-bb_inf)/(bb_sup-bb_inf)) if bb_sup>bb_inf else 0.5
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
                "Previsao": int(previsao),
                "resultado": None
            }
            guardar_previsao_firestore(registo)

            if previsao:
                sinais = [s for s in [
                    "RSI < 30" if rsi<30 else None,
                    "preço>EMA" if preco>ema else None,
                    "MACD>sinal" if macd_val>macd_sig else None,
                    "volume alto" if vol>vol_med else None,
                    "fora da BB inf" if preco<bb_inf else None
                ] if s]
                guardar_estrategia_firestore(moeda, "ENTRADA", preco, ", ".join(sinais), rsi, (preco-ema)/ema*100)
                registo["Mensagem"] = f"🚨 {moeda}: RSI={rsi:.2f}, EMA={ema:.2f}, MACD={macd_val:.2f}/{macd_sig:.2f}"
                oportunidades.append(registo)

        except Exception as e:
            print(f"⚠️ Erro analisar {moeda}: {e}")

    for msg in sorted(oportunidades, key=lambda x: -abs(x['MACD_diff']))[:MAX_ALERTAS_POR_CICLO]:
        enviar_telegram(msg['Mensagem'])


def acompanhar_posicoes(exchange, posicoes):
    global ULTIMO_RESUMO
    agora = datetime.now()
    linhas = []
    for pos in posicoes:
        try:
            ticker = exchange.fetch_ticker(pos['moeda'])
            preco_atual = ticker['last']
            valor_atual = preco_atual*(pos['montante']/pos['preco_entrada'])
            lucro = valor_atual - pos['montante']
            percent = (lucro/pos['montante'])*100
            linhas.append(f"{pos['moeda']}: {percent:.2f}%")
        except Exception:
            pass
    if (agora - ULTIMO_RESUMO).total_seconds() > INTERVALO_RESUMO_HORAS*3600:
        if linhas:
            enviar_telegram("\n".join(linhas))
        ULTIMO_RESUMO = agora


def atualizar_documentos_firestore():
    try:
        for doc in db.collection("historico_previsoes").stream():
            data = doc.to_dict()
            if "resultado" not in data:
                db.collection("historico_previsoes").document(doc.id).set({"resultado": None}, merge=True)
    except Exception as e:
        print(f"❌ Erro ao atualizar docs: {e}")

def iniciar_bot():
    exchange = ccxt.kucoin()
    exchange.load_markets()
    moedas = [s for s in exchange.symbols if "/USDT" in s]
    while True:
        atualizar_documentos_firestore()
        analisar_oportunidades(exchange, moedas, modelo)
        acompanhar_posicoes(exchange, carregar_posicoes())
        time.sleep(3600)

threading.Thread(target=iniciar_bot, daemon=True).start()

# 🟢 Execução principal
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Iniciando Flask na porta {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
