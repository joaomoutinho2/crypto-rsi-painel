﻿"""
🔍 Bot de Análise de Oportunidades (Máximo 5 Alertas por Hora)

Este bot:
- Usa modelo ML treinado para prever oportunidades de entrada
- Analisa TODAS as moedas USDT
- Ordena oportunidades pela sua força (indicadores técnicos)
- Envia no máximo 5 alertas por hora
- Não envia nada se não houver oportunidades realmente boas
"""

import os
import joblib
import ccxt
import pandas as pd
import time
import base64
import io
from datetime import datetime, timedelta
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands

from firebase_config import iniciar_firebase
from firebase_admin import firestore
from telegram_alert import enviar_telegram
from chatgpt_analise import avaliar_com_chatgpt

# 🔧 Parâmetros de Simulação
orcamento_inicial = 1000.0
saldo_virtual = orcamento_inicial
investimento_por_operacao = 0.05  # 5%
posicoes_virtuais = []
lucros_virtuais = []

# 🔐 Inicializar Firebase
db = iniciar_firebase()

# 📥 Funções de Saldo
def carregar_saldo_virtual():
    try:
        doc = db.collection("estado_simulacao").document("saldo_virtual").get()
        if doc.exists:
            return doc.to_dict().get("valor", 1000.0)
    except Exception as e:
        print(f"⚠️ Erro ao carregar saldo_virtual: {e}")
    return 1000.0

def guardar_saldo_virtual(valor):
    try:
        db.collection("estado_simulacao").document("saldo_virtual").set({
            "valor": round(valor, 2)
        })
    except Exception as e:
        print(f"❌ Erro ao guardar saldo_virtual: {e}")

# 🧠 Carregar Modelo ML
def carregar_modelo_firestore():
    try:
        docs = db.collection("modelos_treinados").order_by("data_treino", direction=firestore.Query.DESCENDING).limit(1).stream()
        for doc in docs:
            dados = doc.to_dict()
            if "modelo" in dados:
                binario = base64.b64decode(dados["modelo"])
                modelo = joblib.load(io.BytesIO(binario))
                print("✅ Modelo carregado do Firestore.")
                return modelo
        print("⚠️ Nenhum modelo encontrado no Firestore.")
        return None
    except Exception as e:
        print(f"❌ Erro ao carregar modelo do Firestore: {e}")
        return None

# 📤 Atualizar previsões pendentes
def atualizar_resultados_firestore(modelo):
    docs = db.collection("historico_previsoes").where("resultado", "==", "pendente").stream()
    for doc in docs:
        data = doc.to_dict()
        campos = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position"]
        if all(c in data for c in campos):
            entrada = pd.DataFrame([data])[campos]
            pred = modelo.predict(entrada)[0]
            db.document(doc.reference.path).update({"resultado": float(pred)})

# 📊 Funções Auxiliares
def carregar_posicoes():
    docs = db.collection("posicoes").stream()
    return [doc.to_dict() for doc in docs]

def carregar_posicoes_virtuais():
    try:
        docs = db.collection("posicoes_virtuais").stream()
        return [(doc.id, doc.to_dict()) for doc in docs]
    except Exception as e:
        print(f"❌ Erro ao carregar posicoes_virtuais: {e}")
        return []

def guardar_previsao(simbolo, entrada, previsao):
    dados = {
        **entrada.to_dict(orient="records")[0],
        "simbolo": simbolo,
        "previsao": float(previsao),
        "resultado": "pendente",
        "timestamp": datetime.utcnow()
    }
    db.collection("historico_previsoes").add(dados)

def contagem_alertas_ultima_hora():
    uma_hora_atras = datetime.utcnow() - timedelta(hours=1)
    docs = db.collection("historico_previsoes").where("timestamp", ">=", uma_hora_atras).stream()
    return sum(1 for doc in docs if doc.to_dict().get("previsao") == 1)

# 🎯 Função de cálculo de objetivo
def calcular_objetivo_volatilidade(df, fator=3.0, objetivo_minimo=2.5):
    volatilidades = (df['high'] - df['low']) / df['low'] * 100
    media_volatilidade = volatilidades.rolling(window=14).mean().iloc[-1]
    objetivo = round(media_volatilidade * fator, 2)
    return max(objetivo, objetivo_minimo)

# 🚨 Verificação de vendas simuladas
def verificar_saidas_virtuais(exchange):
    global saldo_virtual
    encerradas = []

    for doc_id, pos in carregar_posicoes_virtuais():
        simbolo = pos["simbolo"]
        try:
            ticker = exchange.fetch_ticker(simbolo)
            preco_atual = ticker["last"]
            preco_entrada = pos["preco_entrada"]
            objetivo = pos["objetivo"]
            quantidade = pos["quantidade"]

            lucro_percentual = ((preco_atual - preco_entrada) / preco_entrada) * 100
            stop_loss = -5.0

            if lucro_percentual >= objetivo or lucro_percentual <= stop_loss:
                valor_final = preco_atual * quantidade
                saldo_virtual += valor_final

                motivo = "objetivo" if lucro_percentual >= objetivo else "stop-loss"
                print(f"💰 VENDA ({motivo.upper()}): {simbolo} | Lucro: {lucro_percentual:.2f}%")

                db.collection("simulacoes_vendas").add({
                    "simbolo": simbolo,
                    "preco_entrada": preco_entrada,
                    "preco_venda": round(preco_atual, 4),
                    "quantidade": round(quantidade, 6),
                    "lucro": round(valor_final - pos["valor_investido"], 2),
                    "data_venda": datetime.utcnow().isoformat(),
                    "encerrado_por": motivo
                })

                db.collection("posicoes_virtuais").document(doc_id).delete()
                encerradas.append(simbolo)

        except Exception as e:
            print(f"⚠️ Erro ao verificar venda virtual para {simbolo}: {e}")

    if encerradas:
        guardar_saldo_virtual(saldo_virtual)
        print(f"💾 Saldo atualizado após vendas: {saldo_virtual:.2f} USDT")

# 🤖 Analisar oportunidades e enviar alertas
def analisar_oportunidades(modelo):
    exchange = ccxt.kucoin()
    exchange.load_markets()
    symbols = [s for s in exchange.symbols if s.endswith("/USDT")]

    moedas_em_posicao = {p['simbolo'] for p in carregar_posicoes() if 'simbolo' in p}
    oportunidades = []

    for simbolo in symbols:
        if simbolo in moedas_em_posicao:
            continue

        try:
            time.sleep(0.2)
            ohlcv = exchange.fetch_ohlcv(simbolo, timeframe="1h", limit=100)
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

            if df.empty or len(df) < 30:
                continue

            df["RSI"] = RSIIndicator(df["close"]).rsi()
            df["EMA"] = EMAIndicator(df["close"]).ema_indicator()
            df["EMA_diff"] = df["close"] - df["EMA"]
            macd = MACD(df["close"])
            df["MACD"] = macd.macd()
            df["MACD_signal"] = macd.macd_signal()
            df["MACD_diff"] = macd.macd_diff()
            bb = BollingerBands(df["close"])
            df["BB_upper"] = bb.bollinger_hband()
            df["BB_lower"] = bb.bollinger_lband()
            df["BB_position"] = (df["close"] - df["BB_lower"]) / (df["BB_upper"] - df["BB_lower"])
            df["volume_medio"] = df["volume"].rolling(window=14).mean()
            df.dropna(inplace=True)

            if df.empty:
                continue

            row = df.iloc[-1]
            entrada = row[["RSI", "EMA_diff", "MACD_diff", "volume", "BB_position"]].rename({"volume": "Volume_relativo"}).to_frame().T
            previsao = modelo.predict(entrada)[0]

            if previsao == 1:
                objetivo = calcular_objetivo_volatilidade(df)
                força = abs(row["RSI"] - 50) + abs(row["MACD_diff"]) + abs(row["BB_position"] - 0.5)
                oportunidades.append((simbolo, entrada, força, row, objetivo))
                comentario = avaliar_com_chatgpt(simbolo, row["RSI"], row["MACD_diff"], row["volume"], objetivo)

        except Exception as e:
            print(f"⚠️ Erro ao analisar {simbolo}: {e}")

    oportunidades.sort(key=lambda x: x[2], reverse=True)
    restantes = 5 - contagem_alertas_ultima_hora()
    if restantes <= 0:
        print("⏳ Limite de alertas por hora atingido.")
        return

    for simbolo, entrada, _, row, objetivo in oportunidades[:restantes]:
        global saldo_virtual
        preco = row["close"]
        valor_investido = round(saldo_virtual * investimento_por_operacao, 2)
        if valor_investido < 10:
            print(f"⛔ Saldo virtual muito baixo para investir em {simbolo}.")
            continue

        quantidade = valor_investido / preco
        saldo_virtual -= valor_investido
        guardar_saldo_virtual(saldo_virtual)

        mensagem = (
            f"🚨 Oportunidade: {simbolo}\n"
            f"💰 Preço: {preco:.2f} USDT\n"
            f"📊 RSI: {row['RSI']:.2f} | EMA: {row['EMA']:.2f}\n"
            f"📈 MACD: {row['MACD']:.2f} / Sinal: {row['MACD_signal']:.2f}\n"
            f"📉 Volume: {row['volume']:.2f} (média: {row['volume_medio']:.2f})\n"
            f"🎯 Bollinger: [{row['BB_lower']:.2f} ~ {row['BB_upper']:.2f}]\n"
            f"📌 Objetivo sugerido: {objetivo:.2f}%\n"
            f"💼 Simulado: Investir {valor_investido:.2f} → {quantidade:.6f} unidades\n"
            f"\n🧠 GPT diz: {comentario}"
            f"\n⚙️ Entrada considerada promissora ✅"
        )
        enviar_telegram(mensagem)

        doc = entrada.to_dict(orient="records")[0]
        doc.update({
            "simbolo": simbolo,
            "previsao": 1,
            "resultado": "pendente",
            "objetivo": objetivo,
            "timestamp": datetime.utcnow()
        })
        db.collection("historico_previsoes").add(doc)

        posicoes_virtuais.append({
            "simbolo": simbolo,
            "quantidade": quantidade,
            "valor_investido": valor_investido,
            "preco_entrada": preco,
            "objetivo": objetivo,
            "data": datetime.utcnow()
        })

    print(f"✅ Enviados {min(restantes, len(oportunidades))} alertas nesta execução.")
    print(f"📊 Capital restante (simulado): {saldo_virtual:.2f} USDT | Operações simuladas: {len(posicoes_virtuais)}")

# 🚀 Execução Principal
def main():
    global saldo_virtual
    saldo_virtual = carregar_saldo_virtual()
    print(f"💰 Saldo inicial carregado: {saldo_virtual:.2f} USDT")

    modelo = carregar_modelo_firestore()
    if modelo is None:
        print("❌ Sem modelo disponível. Abortando execução.")
        return

    atualizar_resultados_firestore(modelo)
    analisar_oportunidades(modelo)
    verificar_saidas_virtuais(ccxt.kucoin())
    guardar_saldo_virtual(saldo_virtual)
    print(f"💼 Saldo após verificações: {saldo_virtual:.2f} USDT")

if __name__ == "__main__":
    main()
