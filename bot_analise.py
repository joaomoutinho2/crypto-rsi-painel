"""
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
from datetime import datetime, timedelta
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands

from firebase_config import iniciar_firebase
from telegram_alert import enviar_telegram

orcamento_inicial = 1000.0
saldo_virtual = orcamento_inicial
investimento_por_operacao = 0.05  # 5% do capital atual
posicoes_virtuais = []
lucros_virtuais = []

# Inicializa Firebase
db = iniciar_firebase()

# 🔁 Atualizar documentos pendentes com previsão
def atualizar_resultados_firestore(modelo):
    docs = db.collection("historico_previsoes").where("resultado", "==", "pendente").stream()
    for doc in docs:
        data = doc.to_dict()
        campos = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position"]
        if all(c in data for c in campos):
            entrada = pd.DataFrame([data])[campos]
            pred = modelo.predict(entrada)[0]
            db.document(doc.reference.path).update({"resultado": float(pred)})

# 📊 Carregar posições existentes
def carregar_posicoes():
    docs = db.collection("posicoes").stream()
    return [doc.to_dict() for doc in docs]

# 🔥 Guardar previsão

def guardar_previsao(simbolo, entrada, previsao):
    dados = {
        **entrada.to_dict(orient="records")[0],
        "simbolo": simbolo,
        "previsao": float(previsao),
        "resultado": "pendente",
        "timestamp": datetime.utcnow()
    }
    db.collection("historico_previsoes").add(dados)

# 🔎 Verificar quantos alertas já foram enviados na última hora
def contagem_alertas_ultima_hora():
    uma_hora_atras = datetime.utcnow() - timedelta(hours=1)
    docs = db.collection("historico_previsoes").where("timestamp", ">=", uma_hora_atras).stream()
    return sum(1 for doc in docs if doc.to_dict().get("previsao") == 1)

def verificar_saidas_virtuais(exchange):
    global saldo_virtual
    encerradas = []

    for pos in posicoes_virtuais:
        simbolo = pos["simbolo"]
        try:
            ticker = exchange.fetch_ticker(simbolo)
            preco_atual = ticker["last"]
            preco_entrada = pos["preco_entrada"]
            objetivo = pos["objetivo"]

            lucro_percentual = ((preco_atual - preco_entrada) / preco_entrada) * 100
            stop_loss = -5.0  # nova regra de saída por perda

            if lucro_percentual >= objetivo or lucro_percentual <= stop_loss:
                valor_final = preco_atual * pos["quantidade"]
                saldo_virtual += valor_final

                motivo = "objetivo" if lucro_percentual >= objetivo else "stop-loss"
                print(f"💰 VENDA ({motivo.upper()}): {simbolo} | Lucro: {lucro_percentual:.2f}%")

                db.collection("simulacoes_vendas").add({
                    "simbolo": simbolo,
                    "preco_entrada": preco_entrada,
                    "preco_venda": round(preco_atual, 4),
                    "quantidade": round(pos["quantidade"], 6),
                    "lucro": round(valor_final - pos["valor_investido"], 2),
                    "data_venda": datetime.utcnow().isoformat(),
                    "encerrado_por": motivo
                })

                encerradas.append(pos)

        except Exception as e:
            print(f"⚠️ Erro ao verificar venda virtual para {simbolo}: {e}")

    for encerrada in encerradas:
        preco_entrada = encerrada["preco_entrada"]
        quantidade = encerrada["quantidade"]
        preco_venda = exchange.fetch_ticker(encerrada["simbolo"])["last"]
        valor_final = preco_venda * quantidade
        lucro = valor_final - encerrada["valor_investido"]

        db.collection("simulacoes_vendas").add({
            "simbolo": encerrada["simbolo"],
            "preco_entrada": preco_entrada,
            "preco_venda": round(preco_venda, 4),
            "quantidade": round(quantidade, 6),
            "lucro": round(lucro, 2),
            "data_venda": datetime.utcnow().isoformat()
        })

        posicoes_virtuais.remove(encerrada)

# 🧠 Analisar e enviar até 5 melhores oportunidades
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

        # Simular investimento
        valor_investido = round(saldo_virtual * investimento_por_operacao, 2)
        if valor_investido < 10:
            print(f"⛔ Saldo virtual muito baixo para investir em {simbolo}.")
            continue

        quantidade = valor_investido / preco
        saldo_virtual -= valor_investido

        mensagem = (
            f"🚨 Oportunidade: {simbolo}\n"
            f"💰 Preço: {preco:.2f} USDT\n"
            f"📊 RSI: {row['RSI']:.2f} | EMA: {row['EMA']:.2f}\n"
            f"📈 MACD: {row['MACD']:.2f} / Sinal: {row['MACD_signal']:.2f}\n"
            f"📉 Volume: {row['volume']:.2f} (média: {row['volume_medio']:.2f})\n"
            f"🎯 Bollinger: [{row['BB_lower']:.2f} ~ {row['BB_upper']:.2f}]\n"
            f"📌 Objetivo sugerido: {objetivo:.2f}%\n"
            f"💼 Simulado: Investir {valor_investido:.2f} → {quantidade:.6f} unidades\n"
            f"⚙️ Entrada considerada promissora ✅"
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

        # Guardar posição simulada
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

# 🎯 Função para calcular objetivo automaticamente com base na volatilidade

def calcular_objetivo_volatilidade(df, fator=3.0, objetivo_minimo=2.5):
    volatilidades = (df['high'] - df['low']) / df['low'] * 100
    media_volatilidade = volatilidades.rolling(window=14).mean().iloc[-1]
    objetivo = round(media_volatilidade * fator, 2)
    return max(objetivo, objetivo_minimo)

# 🚀 Execução principal
def main():
    try:
        modelo = joblib.load("modelo_treinado.pkl")
    except Exception as e:
        print(f"❌ Erro ao carregar modelo: {e}")
        return

    atualizar_resultados_firestore(modelo)
    analisar_oportunidades(modelo)
    verificar_saidas_virtuais(ccxt.kucoin())
    print(f"💼 Saldo após verificações: {saldo_virtual:.2f} USDT")

if __name__ == "__main__":
    main()
