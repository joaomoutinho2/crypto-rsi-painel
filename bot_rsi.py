# bot_rsi.py — Background Worker otimizado para Render (2GB RAM)
import os, time, joblib, ccxt, pandas as pd, traceback, gc
from datetime import datetime, timedelta
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands
from config import TIMEFRAME
from firebase_config import iniciar_firebase
from treino_modelo_firebase import treinar_modelo_automaticamente

db = iniciar_firebase()
modelo = None

# Constantes
QUEDA_LIMITE = 0.95
INTERVALO_RESUMO_HORAS = 2
INTERVALO_TREINO_DIAS = 1
INTERVALO_AVALIACAO_HORAS = 2
ULTIMO_RESUMO = datetime.now() - pd.to_timedelta(INTERVALO_RESUMO_HORAS, unit="h")
ULTIMO_TREINO = datetime.now() - timedelta(days=2)
ULTIMA_AVALIACAO_RESULTADO = datetime.now() - timedelta(hours=3)
MAX_ALERTAS_POR_CICLO = 5

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def enviar_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except: pass

def guardar_previsao_firestore(reg):
    if not reg.get("Moeda") or reg.get("preco_entrada") is None: return
    try: db.collection("historico_previsoes").add(reg)
    except: pass

def guardar_estrategia_firestore(moeda, direcao, preco, sinais, rsi, variacao):
    try:
        db.collection("estrategias").add({
            "Moeda": moeda, "Direcao": direcao, "Preço": preco,
            "Sinais": sinais, "RSI": rsi, "Variação (%)": variacao,
            "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except: pass

def carregar_posicoes():
    try: return [doc.to_dict() for doc in db.collection("posicoes").stream()]
    except: return []

def atualizar_precos_de_entrada(exchange, timeframe="1h", limite=50):
    colecao = db.collection("historico_previsoes").order_by("Data")
    ultimo_doc = None
    while True:
        query = colecao.limit(limite)
        if ultimo_doc: query = query.start_after(ultimo_doc)
        docs = query.get()
        if not docs: break
        for doc in docs:
            data = doc.to_dict()
            if "preco_entrada" in data: continue
            moeda = data.get("Moeda"); data_str = data.get("Data")
            if not moeda or not data_str: continue
            try:
                dt = datetime.strptime(data_str, "%Y-%m-%d %H:%M:%S")
                timestamp = int(time.mktime((dt - timedelta(minutes=5)).timetuple())) * 1000
                candles = exchange.fetch_ohlcv(moeda, timeframe=timeframe, since=timestamp, limit=5)
                if candles:
                    preco = min(candles, key=lambda x: abs(x[0] - int(dt.timestamp() * 1000)))[4]
                    doc.reference.set({"preco_entrada": preco}, merge=True)
            except: continue
        ultimo_doc = docs[-1]

def atualizar_documentos_firestore(limite=100):
    colecao = db.collection("historico_previsoes")
    ultimo_doc = None
    while True:
        query = colecao.limit(limite)
        if ultimo_doc: query = query.start_after(ultimo_doc)
        docs = list(query.stream())
        if not docs: break
        for doc in docs:
            data = doc.to_dict()
            if "resultado" not in data:
                doc.reference.set({"resultado": None}, merge=True)
        ultimo_doc = docs[-1]

def analisar_oportunidades(exchange, moedas):
    oportunidades = []
    for moeda in moedas[:200]:
        try:
            df = pd.DataFrame(exchange.fetch_ohlcv(moeda, timeframe=TIMEFRAME, limit=100),
                              columns=["t", "open", "high", "low", "close", "volume"])
            df["RSI"] = RSIIndicator(close=df["close"]).rsi()
            df["EMA"] = EMAIndicator(close=df["close"]).ema_indicator()
            macd = MACD(close=df["close"])
            df["MACD"] = macd.macd(); df["MACD_signal"] = macd.macd_signal()
            df["vol_med"] = df["volume"].rolling(14).mean()
            bb = BollingerBands(close=df["close"])
            df["BB_inf"] = bb.bollinger_lband(); df["BB_sup"] = bb.bollinger_hband()

            rsi = df["RSI"].iat[-1]; preco = df["close"].iat[-1]; ema = df["EMA"].iat[-1]
            macd_val = df["MACD"].iat[-1]; macd_sig = df["MACD_signal"].iat[-1]
            vol = df["volume"].iat[-1]; vol_med = df["vol_med"].iat[-1] or 1
            bb_inf = df["BB_inf"].iat[-1]; bb_sup = df["BB_sup"].iat[-1]

            entrada = pd.DataFrame([{
                "RSI": rsi,
                "EMA_diff": (preco - ema) / ema if ema else 0,
                "MACD_diff": macd_val - macd_sig,
                "Volume_relativo": vol / vol_med,
                "BB_position": (preco - bb_inf) / (bb_sup - bb_inf) if bb_sup > bb_inf else 0.5
            }])

            previsao = modelo.predict(entrada)[0] if modelo else 0.0
            registo = {
                "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Moeda": moeda, "preco_entrada": preco,
                **entrada.iloc[0].to_dict(),
                "Previsao": previsao, "resultado": None
            }
            guardar_previsao_firestore(registo)

            if previsao > 1.0:
                sinais = ", ".join(filter(None, [
                    "RSI<30" if rsi < 30 else None,
                    "preço>EMA" if preco > ema else None,
                    "MACD>sinal" if macd_val > macd_sig else None,
                    "volume↑" if vol > vol_med else None,
                    "abaixo BB" if preco < bb_inf else None
                ]))
                oportunidades.append((abs(macd_val - macd_sig),
                    f"🚨 {moeda}: Prev={previsao:+.2f}% | RSI={rsi:.2f} MACD={macd_val:.2f}/{macd_sig:.2f} | {sinais}"))
                guardar_estrategia_firestore(moeda, "ENTRADA", preco, sinais, rsi, previsao)
        except: continue

    oportunidades.sort(reverse=True)
    for _, msg in oportunidades[:MAX_ALERTAS_POR_CICLO]:
        enviar_telegram(msg)
    gc.collect()

def avaliar_resultados(exchange, limite=1000):
    colecao = db.collection("historico_previsoes")
    ultimo_doc = None
    while True:
        query = colecao.limit(limite)
        if ultimo_doc: query = query.start_after(ultimo_doc)
        docs = list(query.stream())
        if not docs: break
        for doc in docs:
            data = doc.to_dict(); doc_id = doc.id; ultimo_doc = doc
            if data.get("resultado") not in [None, "pendente", "null", ""]:
                continue
            if data.get("avaliado_em"):
                try:
                    if datetime.now() - datetime.strptime(data["avaliado_em"], "%Y-%m-%d %H:%M:%S") < timedelta(hours=24):
                        continue
                except: pass
            moeda = data.get("Moeda"); preco = data.get("preco_entrada")
            if not moeda or preco is None: continue
            try:
                preco_atual = exchange.fetch_ticker(moeda)["last"]
                resultado = round((preco_atual - preco) / preco * 100, 2)
                db.collection("historico_previsoes").document(doc_id).update({
                    "resultado": resultado,
                    "avaliado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            except: continue

def existem_previsoes_pendentes():
    try:
        docs = db.collection("historico_previsoes").where("resultado", "in", [None, "pendente", ""]).limit(1).stream()
        return any(True for _ in docs)
    except: return False

def acompanhar_posicoes(exchange, posicoes):
    global ULTIMO_RESUMO
    if datetime.now() - ULTIMO_RESUMO < timedelta(hours=INTERVALO_RESUMO_HORAS): return
    linhas = []
    for pos in posicoes:
        try:
            preco = exchange.fetch_ticker(pos["moeda"])["last"]
            entrada = pos["preco_entrada"]; montante = pos["montante"]
            lucro = preco * (montante / entrada) - montante
            percent = (lucro / montante) * 100
            linhas.append(f"{pos['moeda']}: {percent:+.2f}% | Entrada: {entrada:.4f} | Atual: {preco:.4f} | Lucro: {lucro:+.2f} USDT")
        except: continue
    if linhas:
        enviar_telegram("📈 Atualização de posições:\n" + "\n".join(linhas))
    ULTIMO_RESUMO = datetime.now()

def thread_bot():
    global modelo, ULTIMO_TREINO, ULTIMA_AVALIACAO_RESULTADO
    try:
        print("🚀 Iniciando bot como Background Worker...")
        exchange = ccxt.kucoin({"enableRateLimit": True, "options": {"adjustForTimeDifference": True}})
        exchange.load_markets()
        moedas = [s for s in exchange.symbols if s.endswith("/USDT")]
        atualizar_precos_de_entrada(exchange, limite=50)
        atualizar_documentos_firestore(limite=100)
        modelo = treinar_modelo_automaticamente()
        enviar_telegram("🔔 Bot RSI iniciado no Render (Background Worker)")

        while True:
            agora = datetime.now()
            if (agora - ULTIMO_TREINO).days >= INTERVALO_TREINO_DIAS:
                modelo = treinar_modelo_automaticamente()
                ULTIMO_TREINO = agora

            if (agora - ULTIMA_AVALIACAO_RESULTADO).total_seconds() > INTERVALO_AVALIACAO_HORAS * 3600:
                if existem_previsoes_pendentes():
                    avaliar_resultados(exchange)
                    ULTIMA_AVALIACAO_RESULTADO = agora

            atualizar_precos_de_entrada(exchange, limite=50)
            atualizar_documentos_firestore(limite=100)
            analisar_oportunidades(exchange, moedas)
            acompanhar_posicoes(exchange, carregar_posicoes())
            time.sleep(3600)

    except Exception as exc:
        traceback.print_exc()
        enviar_telegram(f"❌ Erro no bot: {exc}")

if __name__ == "__main__":
    thread_bot()
