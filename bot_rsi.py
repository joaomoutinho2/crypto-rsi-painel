# bot_rsi.py — Versão Corrigida e Otimizada para Background Worker no Render
# --------------------------------------------------
print("🔍 Testando imports...")
try:
    import os
    print("✅ Importado: os")
    import time
    print("✅ Importado: time")
    import joblib
    print("✅ Importado: joblib")
    import ccxt
    print("✅ Importado: ccxt")
    import pandas as pd
    print("✅ Importado: pandas")
    import traceback
    print("✅ Importado: traceback")
    from datetime import datetime, timedelta
    print("✅ Importado: datetime, timedelta")
    from ta.momentum import RSIIndicator
    print("✅ Importado: RSIIndicator")
    from ta.trend import EMAIndicator, MACD
    print("✅ Importado: EMAIndicator, MACD")
    from ta.volatility import BollingerBands
    print("✅ Importado: BollingerBands")
    from config import TIMEFRAME
    print("✅ Importado: TIMEFRAME")
except Exception as e:
    print(f"❌ Erro ao importar: {e}")

print("🔍 Testando inicialização do Firebase...")
try:
    from firebase_config import iniciar_firebase
    db = iniciar_firebase()
    print("✅ Firebase inicializado com sucesso.")
except Exception as e:
    print(f"❌ Erro ao inicializar o Firebase: {e}")

# 🔹 Constantes globais
db = None
modelo = None
MODELO_PATH = "modelo_treinado.pkl"

QUEDA_LIMITE = 0.95
OBJETIVO_PADRAO = 10
INTERVALO_RESUMO_HORAS = 2
MAX_ALERTAS_POR_CICLO = 5
ULTIMO_RESUMO = datetime.now() - pd.to_timedelta(INTERVALO_RESUMO_HORAS, unit="h")
ULTIMO_TREINO = datetime.now() - timedelta(days=2)
INTERVALO_TREINO_DIAS = 1
ULTIMA_AVALIACAO_RESULTADO = datetime.now() - timedelta(hours=3)
INTERVALO_AVALIACAO_HORAS = 2

# 🔔 Telegram
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
        response = requests.post(url, data=data)
        print(f"📤 Enviando para Telegram: {mensagem}")
        print(f"📨 Status: {response.status_code} / Resposta: {response.text}")
    except Exception as e:
        print(f"❌ Telegram: {e}")


# 🔁 Helpers Firestore
def guardar_previsao_firestore(reg):
    if db is None:
        return
    if not reg.get("Moeda") or reg.get("preco_entrada") is None:
        print(f"⚠️ Ignorando previsão incompleta: {reg}")
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

def atualizar_documentos_firestore(limite=1000):
    if db is None:
        return
    print("🔁 A atualizar documentos sem campo 'resultado'...")
    try:
        colecao = db.collection("historico_previsoes")
        ultimo_doc = None
        total_atualizados = 0

        while True:
            query = colecao.limit(limite)
            if ultimo_doc:
                query = query.start_after(ultimo_doc)

            docs = list(query.stream())
            if not docs:
                break

            for doc in docs:
                data = doc.to_dict()
                if "resultado" not in data:
                    doc.reference.set({"resultado": None}, merge=True)
                    total_atualizados += 1

            ultimo_doc = docs[-1]

        print(f"✅ {total_atualizados} documentos atualizados com campo 'resultado: None'.")

    except Exception as exc:
        print(f"❌ Erro ao atualizar documentos: {exc}")


def atualizar_precos_de_entrada(exchange, timeframe="1h", limite=1000):
    print("🛠️ Atualizando documentos antigos com campo 'preco_entrada'...")
    try:
        colecao = db.collection("historico_previsoes").order_by("Data")
        ultimo_doc = None
        atualizados = 0
        total = 0

        while True:
            query = colecao.limit(limite)
            if ultimo_doc:
                query = query.start_after(ultimo_doc)

            docs = query.get()
            if not docs:
                break

            for doc in docs:
                total += 1
                data = doc.to_dict()
                ref = doc.reference

                if "preco_entrada" in data:
                    continue

                moeda = data.get("Moeda")
                data_str = data.get("Data")

                try:
                    if not moeda or not data_str:
                        continue

                    dt = datetime.strptime(data_str, "%Y-%m-%d %H:%M:%S")
                    timestamp = int(time.mktime((dt - timedelta(minutes=5)).timetuple())) * 1000
                    candles = exchange.fetch_ohlcv(moeda, timeframe=timeframe, since=timestamp, limit=5)
                    if not candles:
                        continue

                    candle_proximo = min(candles, key=lambda x: abs(x[0] - int(dt.timestamp() * 1000)))
                    preco_close = candle_proximo[4]
                    ref.set({"preco_entrada": preco_close}, merge=True)
                    atualizados += 1

                except Exception as e:
                    print(f"⚠️ Erro em {moeda} @ {data_str}: {e}")

            ultimo_doc = docs[-1]

        print(f"📊 {atualizados}/{total} documentos atualizados com 'preco_entrada'.")

    except Exception as e:
        print(f"❌ Erro ao atualizar preços de entrada: {e}")


def analisar_oportunidades(exchange, moedas):
    from ta.momentum import RSIIndicator
    from ta.trend import EMAIndicator, MACD
    from ta.volatility import BollingerBands

    print("🧪 [DEBUG] analisar_oportunidades começou...")
    oportunidades = []

    for moeda in moedas:
        print(f"🧪 [DEBUG] Analisando {moeda}")
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

            # Extrair os últimos valores
            rsi = df["RSI"].iat[-1]
            preco = df["close"].iat[-1]
            ema = df["EMA"].iat[-1]
            macd = df["MACD"].iat[-1]
            macd_sig = df["MACD_signal"].iat[-1]
            vol = df["volume"].iat[-1]
            vol_med = df["vol_med"].iat[-1] or 1
            bb_inf = df["BB_inf"].iat[-1]
            bb_sup = df["BB_sup"].iat[-1]

            # Calcular variáveis de entrada
            entrada = pd.DataFrame([{
                "RSI": rsi,
                "EMA_diff": (preco - ema) / ema if ema != 0 else 0,
                "MACD_diff": macd - macd_sig,
                "Volume_relativo": vol / vol_med,
                "BB_position": (preco - bb_inf) / (bb_sup - bb_inf) if bb_sup > bb_inf else 0.5,
            }])

            # Previsão
            prev_array = modelo.predict(entrada) if modelo else [0]
            prev = int(prev_array[0]) if prev_array[0] in [0, 1] else 0
            print(f"🧪 [DEBUG] Previsão: {prev}")

            # Guardar no Firestore
            registo = {
                "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Moeda": moeda,
                "preco_entrada": preco,
                **entrada.iloc[0].to_dict(),
                "Previsao": prev,
                "resultado": None  # Será calculado quando a posição for fechada
            }
            guardar_previsao_firestore(registo)

            # Só alerta se previsão for positiva
            if prev == 1:
                sinais = ", ".join(filter(None, [
                    "RSI<30" if rsi < 30 else None,
                    "preço>EMA" if preco > ema else None,
                    "MACD>sinal" if macd > macd_sig else None,
                    "volume↑" if vol > vol_med else None,
                    "abaixo BB" if preco < bb_inf else None
                ]))

                oportunidades.append((
                    abs(entrada["MACD_diff"].iloc[0]),
                    f"🚨 {moeda}: RSI={rsi:.2f} MACD={macd:.2f}/{macd_sig:.2f} | {sinais}"
                ))

                guardar_estrategia_firestore(moeda, "ENTRADA", preco, sinais, rsi, (preco - ema) / ema * 100)

        except Exception as exc:
            print(f"⚠️ Erro ao analisar {moeda}: {exc}")

    # Enviar apenas top N oportunidades ordenadas por força do MACD
    oportunidades.sort(reverse=True)
    for _, mensagem in oportunidades[:MAX_ALERTAS_POR_CICLO]:
        enviar_telegram(mensagem)

def avaliar_resultados(exchange, limite=1000):
    print("📈 A avaliar previsões pendentes...")

    try:
        colecao = db.collection("historico_previsoes")
        ultimo_doc = None
        atualizados = 0
        ignorados = 0
        erros = 0

        while True:
            query = colecao.limit(limite)
            if ultimo_doc:
                query = query.start_after(ultimo_doc)

            docs = list(query.stream())
            if not docs:
                break

            for doc in docs:
                data = doc.to_dict()
                doc_id = doc.id
                ultimo_doc = doc

                if data.get("resultado") not in [None, "pendente", "null", ""]:
                    continue  # já foi avaliado

                moeda = data.get("Moeda")
                preco_entrada = data.get("preco_entrada")

                if not moeda or preco_entrada is None:
                    ignorados += 1
                    print(f"⚠️ Ignorado doc {doc_id} sem moeda ou preco_entrada.")
                    continue

                try:
                    ticker = exchange.fetch_ticker(moeda)
                    preco_atual = ticker["last"]
                    resultado_pct = round((preco_atual - preco_entrada) / preco_entrada * 100, 2)

                    db.collection("historico_previsoes").document(doc_id).update({
                        "resultado": resultado_pct
                    })
                    print(f"✅ Atualizado doc {doc_id} | {moeda}: {resultado_pct:.2f}%")
                    atualizados += 1

                except Exception as e:
                    erros += 1
                    print(f"⚠️ Erro ao obter preço de {moeda} para doc {doc_id}: {e}")

        print(f"\n📊 Atualização concluída:")
        print(f"   ✅ {atualizados} documentos atualizados com resultado (%)")
        print(f"   ⚠️ {ignorados} ignorados por falta de dados")
        print(f"   ❌ {erros} com erro ao obter preço")

    except Exception as exc:
        print(f"❌ Erro ao avaliar previsões: {exc}")



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

def avaliar_previsoes_pendentes():
    print("📈 A avaliar previsões pendentes...")
    try:
        docs = db.collection("historico_previsoes").where("resultado", "==", None).stream()
        documentos = [doc for doc in docs]

        if not documentos:
            print("✅ Nenhum documento pendente.")
            return

        exchange = ccxt.kucoin()
        exchange.load_markets()
        atualizados = 0

        for doc in documentos:
            dados = doc.to_dict()
            doc_ref = doc.reference

            moeda = dados.get("Moeda")
            preco_entrada = dados.get("preco_entrada")

            if not moeda or preco_entrada is None:
                continue

            try:
                ticker = exchange.fetch_ticker(moeda)
                preco_atual = ticker["last"]
                variacao = ((preco_atual - preco_entrada) / preco_entrada) * 100

                doc_ref.update({"resultado": variacao})
                atualizados += 1
                print(f"✅ Atualizado {moeda} com variação {variacao:.2f}%")

            except Exception as e:
                print(f"⚠️ Erro ao obter preço para {moeda}: {e}")

        print(f"📊 {atualizados} documentos atualizados com o campo 'resultado'.")

    except Exception as e:
        print(f"❌ Erro ao avaliar previsões: {e}")
        
def thread_bot():
    global db, modelo, ULTIMO_TREINO, ULTIMA_AVALIACAO_RESULTADO
    try:
        print("🚀 Iniciando bot como Background Worker...")
        from firebase_config import iniciar_firebase
        from treino_modelo_firebase import treinar_modelo_automaticamente

        db = iniciar_firebase()
        print("✅ Firebase inicializado.")

        exchange = ccxt.kucoin({
            "enableRateLimit": True,
            "options": {"adjustForTimeDifference": True},
        })
        exchange.load_markets()
        moedas = [s for s in exchange.symbols if s.endswith("/USDT")]
        print(f"🔁 {len(moedas)} moedas carregadas.")

        atualizar_precos_de_entrada(exchange, limite=50)
        print("✅ Preços de entrada atualizados.")
        atualizar_documentos_firestore(limite=100)
        print("✅ Documentos sem resultado atualizados.")

        print("🧠 A treinar modelo antes de iniciar...")
        modelo = treinar_modelo_automaticamente()
        print("✅ Modelo treinado e carregado.")

        enviar_telegram("🔔 Bot RSI iniciado no Render (Background Worker)")

        while True:
            agora = datetime.now()

            if (agora - ULTIMO_TREINO).days >= INTERVALO_TREINO_DIAS:
                try:
                    modelo = treinar_modelo_automaticamente()
                    ULTIMO_TREINO = agora
                    print("✅ Modelo re-treinado automaticamente.")
                except Exception as e:
                    print(f"⚠️ Erro ao treinar automaticamente: {e}")

            if (agora - ULTIMA_AVALIACAO_RESULTADO).total_seconds() > INTERVALO_AVALIACAO_HORAS * 3600:
                try:
                    avaliar_resultados(exchange)
                    ULTIMA_AVALIACAO_RESULTADO = agora
                except Exception as e:
                    print(f"⚠️ Erro ao avaliar previsões: {e}")

            atualizar_precos_de_entrada(exchange)
            atualizar_documentos_firestore()
            analisar_oportunidades(exchange, moedas)
            acompanhar_posicoes(exchange, carregar_posicoes())

            time.sleep(3600)

    except Exception as exc:
        print(f"❌ Erro fatal no bot: {exc}")
        traceback.print_exc()
        try:
            enviar_telegram(f"❌ Erro no bot: {exc}")
        except:
            pass

if __name__ == "__main__":
    thread_bot()
