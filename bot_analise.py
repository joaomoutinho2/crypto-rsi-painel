
import os
import time
import gc
import joblib
import ccxt
import pandas as pd
from datetime import datetime, timedelta
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands
from config import TIMEFRAME
from firebase_config import iniciar_firebase

# Firebase
db = iniciar_firebase()

# Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def enviar_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram não configurado –", mensagem)
        return
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
        requests.post(url, data=data)
    except Exception as e:
        print(f"❌ Telegram: {e}")

def carregar_posicoes():
    if db is None:
        return []
    try:
        return [doc.to_dict() for doc in db.collection("posicoes").stream()]
    except Exception as e:
        print(f"❌ Erro carregar posições: {e}")
        return []

def guardar_previsao_firestore(reg):
    if db is None:
        return
    if not reg.get("Moeda") or reg.get("preco_entrada") is None:
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

def atualizar_documentos_firestore(limite=20):
    try:
        colecao = db.collection("historico_previsoes")
        docs = colecao.limit(limite).stream()
        for doc in docs:
            data = doc.to_dict()
            if "resultado" not in data:
                doc.reference.set({"resultado": None}, merge=True)
    except Exception as e:
        print(f"❌ Erro ao atualizar documentos: {e}")

def atualizar_precos_de_entrada(exchange, timeframe="1h", limite=20):
    try:
        colecao = db.collection("historico_previsoes").order_by("Data")
        docs = colecao.limit(limite).stream()
        for doc in docs:
            data = doc.to_dict()
            ref = doc.reference
            moeda = data.get("Moeda")
            data_str = data.get("Data")
            if not moeda or not data_str or "preco_entrada" in data:
                continue
            dt = datetime.strptime(data_str, "%Y-%m-%d %H:%M:%S")
            timestamp = int(time.mktime((dt - timedelta(minutes=5)).timetuple())) * 1000
            candles = exchange.fetch_ohlcv(moeda, timeframe=timeframe, since=timestamp, limit=5)
            if candles:
                preco_close = min(candles, key=lambda x: abs(x[0] - int(dt.timestamp() * 1000)))[4]
                ref.set({"preco_entrada": preco_close}, merge=True)
    except Exception as e:
        print(f"❌ Erro ao atualizar preços de entrada: {e}")

def analisar_oportunidades(exchange, moedas, modelo, max_alertas=5):
    moedas = moedas[:30]
    oportunidades = []
    for moeda in moedas:
        try:
            candles = exchange.fetch_ohlcv(moeda, timeframe=TIMEFRAME, limit=100)
            df = pd.DataFrame(candles, columns=["t", "open", "high", "low", "close", "volume"])
            df["RSI"] = RSIIndicator(close=df["close"]).rsi()
            df["EMA"] = EMAIndicator(close=df["close"]).ema_indicator()
            macd_obj = MACD(close=df["close"])
            df["MACD"] = macd_obj.macd()
            df["MACD_signal"] = macd_obj.macd_signal()
            df["vol_med"] = df["volume"].rolling(14).mean()
            bb = BollingerBands(close=df["close"])
            df["BB_inf"] = bb.bollinger_lband()
            df["BB_sup"] = bb.bollinger_hband()
            rsi = df["RSI"].iat[-1]
            preco = df["close"].iat[-1]
            ema = df["EMA"].iat[-1]
            macd = df["MACD"].iat[-1]
            macd_sig = df["MACD_signal"].iat[-1]
            vol = df["volume"].iat[-1]
            vol_med = df["vol_med"].iat[-1] or 1
            bb_inf = df["BB_inf"].iat[-1]
            bb_sup = df["BB_sup"].iat[-1]
            entrada = pd.DataFrame([{
                "RSI": rsi,
                "EMA_diff": (preco - ema) / ema if ema != 0 else 0,
                "MACD_diff": macd - macd_sig,
                "Volume_relativo": vol / vol_med,
                "BB_position": (preco - bb_inf) / (bb_sup - bb_inf) if bb_sup > bb_inf else 0.5,
            }])
            previsao_pct = modelo.predict(entrada)[0] if modelo else 0.0
            registo = {
                "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Moeda": moeda,
                "preco_entrada": preco,
                **entrada.iloc[0].to_dict(),
                "Previsao": previsao_pct,
                "resultado": None
            }
            guardar_previsao_firestore(registo)
            if previsao_pct > 1.0:
                sinais = ", ".join(filter(None, [
                    "RSI<30" if rsi < 30 else None,
                    "preço>EMA" if preco > ema else None,
                    "MACD>sinal" if macd > macd_sig else None,
                    "volume↑" if vol > vol_med else None,
                    "abaixo BB" if preco < bb_inf else None
                ]))
                oportunidades.append((abs(entrada["MACD_diff"].iloc[0]),
                    f"🚨 {moeda}: Prev={previsao_pct:+.2f}% | RSI={rsi:.2f} MACD={macd:.2f}/{macd_sig:.2f} | {sinais}"))
                guardar_estrategia_firestore(moeda, "ENTRADA", preco, sinais, rsi, previsao_pct)
            del df, entrada, candles, macd_obj, bb
            gc.collect()
        except Exception as e:
            print(f"⚠️ Erro ao analisar {moeda}: {e}")
    oportunidades.sort(reverse=True)
    for _, mensagem in oportunidades[:max_alertas]:
        enviar_telegram(mensagem)

def acompanhar_posicoes(exchange, posicoes):
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
            linhas.append(f"{pos['moeda']}: {percent:+.2f}% | Entrada: {preco_entrada:.4f} | Atual: {preco_atual:.4f} | Lucro: {lucro:+.2f} USDT")
        except Exception as e:
            print(f"⚠️ Erro ao acompanhar {pos['moeda']}: {e}")
    if linhas:
        enviar_telegram("📈 Atualização de posições:" + "".join(linhas))

def main():
    modelo = joblib.load("modelo_treinado.pkl")
    exchange = ccxt.kucoin({"enableRateLimit": True})
    exchange.load_markets()
    moedas = [s for s in exchange.symbols if s.endswith("/USDT")][:30]
    atualizar_precos_de_entrada(exchange)
    atualizar_documentos_firestore()
    analisar_oportunidades(exchange, moedas, modelo)
    acompanhar_posicoes(exchange, carregar_posicoes())

if __name__ == "__main__":
    main()
