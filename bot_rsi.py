import time
import ccxt
import pandas as pd
import requests
import os
import json
from datetime import datetime, timedelta
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.volatility import BollingerBands
from flask import Flask
import threading

# ⚙️ Variáveis de ambiente (Render)
from config import MOEDAS, TIMEFRAME, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def registar_estrategia(moeda, direcao, preco, sinais, rsi, sma, ema, macd_val, macd_sig, vol, vol_med, bb_inf, bb_sup):
    try:
        linha = {
            "Data": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Moeda": moeda,
            "Direcao": direcao,
            "Preço": round(preco, 4),
            "Sinais": sinais,
            "RSI": round(rsi, 2),
            "SMA": round(sma, 2),
            "EMA": round(ema, 2),
            "MACD": round(macd_val, 2),
            "MACD_Sinal": round(macd_sig, 2),
            "Volume": round(vol, 2),
            "Volume_Medio": round(vol_med, 2),
            "BB_Inf": round(bb_inf, 2),
            "BB_Sup": round(bb_sup, 2)
        }

        ficheiro = "estrategia_log.csv"
        existe = os.path.exists(ficheiro)
        df = pd.DataFrame([linha])
        df.to_csv(ficheiro, mode='a', header=not existe, index=False)
        print(f"📝 Oportunidade registada: {moeda} ({direcao})")
    except Exception as e:
        print("❌ Erro ao registar oportunidade:", e)

# 📤 Telegram
def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
    try:
        response = requests.post(url, data=data)
        if response.status_code != 200:
            print("❌ Erro Telegram:", response.text)
    except Exception as e:
        print("❌ Exceção Telegram:", e)

# 📁 Carregar moedas registadas
def carregar_moedas_investidas():
    try:
        with open("posicoes.json", "r") as f:
            dados = json.load(f)
            return list(set(p["moeda"] for p in dados))
    except:
        return []

# 📊 Exchange
exchange = ccxt.kucoin()
estado_alertas = {}
ultimo_resumo = {}
INTERVALO_RESUMO_MINUTOS = 60
INTERVALO_RESUMO_HORAS = 2

# 🔍 Análise técnica
def analisar_moeda(moeda, forcar_envio=False):
    try:
        candles = exchange.fetch_ohlcv(moeda, timeframe=TIMEFRAME, limit=100)
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        df['RSI'] = RSIIndicator(close=df['close'], window=14).rsi()
        df['SMA'] = SMAIndicator(close=df['close'], window=14).sma_indicator()
        df['EMA'] = EMAIndicator(close=df['close'], window=14).ema_indicator()
        df['volume_medio'] = df['volume'].rolling(window=14).mean()

        macd = MACD(close=df['close'])
        df['MACD'] = macd.macd()
        df['MACD_signal'] = macd.macd_signal()

        bb = BollingerBands(close=df['close'], window=20, window_dev=2)
        df['BB_upper'] = bb.bollinger_hband()
        df['BB_lower'] = bb.bollinger_lband()

        # Últimos valores
        rsi = df['RSI'].iloc[-1]
        preco = df['close'].iloc[-1]
        sma = df['SMA'].iloc[-1]
        ema = df['EMA'].iloc[-1]
        vol = df['volume'].iloc[-1]
        vol_med = df['volume_medio'].iloc[-1]
        macd_val = df['MACD'].iloc[-1]
        macd_sig = df['MACD_signal'].iloc[-1]
        bb_sup = df['BB_upper'].iloc[-1]
        bb_inf = df['BB_lower'].iloc[-1]

        alerta = "NEUTRO"
        if rsi < 30:
            alerta = "ENTRADA"
        elif rsi > 70:
            alerta = "SAÍDA"

        confirmacoes = []
        if alerta == "ENTRADA":
            if preco > sma: confirmacoes.append("✅ preço > SMA")
            if preco > ema: confirmacoes.append("✅ preço > EMA")
            if vol > vol_med: confirmacoes.append("✅ volume alto")
            if macd_val > macd_sig: confirmacoes.append("✅ MACD p/ cima")
            if preco < bb_inf: confirmacoes.append("✅ abaixo da Bollinger")
        elif alerta == "SAÍDA":
            if preco < sma: confirmacoes.append("✅ preço < SMA")
            if preco < ema: confirmacoes.append("✅ preço < EMA")
            if vol > vol_med: confirmacoes.append("✅ volume alto")
            if macd_val < macd_sig: confirmacoes.append("✅ MACD p/ baixo")
            if preco > bb_sup: confirmacoes.append("✅ acima da Bollinger")
        else:
            confirmacoes.append("ℹ️ RSI neutro")

        analise = " | ".join(confirmacoes)

        mensagem = (
            f"📈 RSI - {moeda} ({TIMEFRAME})\n"
            f"💰 Preço: {preco:.2f} USDT\n"
            f"📊 RSI: {rsi:.2f} | SMA: {sma:.2f} | EMA: {ema:.2f}\n"
            f"📉 Volume: {vol:.2f} (média: {vol_med:.2f})\n"
            f"📊 MACD: {macd_val:.2f} / sinal: {macd_sig:.2f}\n"
            f"📉 Bollinger: [{bb_inf:.2f} ~ {bb_sup:.2f}]\n"
            f"⚠️ Estado: {alerta}\n"
            f"{analise}"
        )

        if forcar_envio:
            enviar_telegram("🕒 *Atualização 2h das posições*\n" + mensagem)
        elif moeda not in estado_alertas or alerta != estado_alertas[moeda]:
            enviar_telegram("🔔 *SINAL MUDOU*\n" + mensagem)
            estado_alertas[moeda] = alerta

        agora = datetime.now()
        if forcar_envio:
            ultimo_resumo[moeda] = agora

    except Exception as e:
        print(f"❌ Erro ao processar {moeda}: {e}")

# 🔁 Loop principal
def avaliar_estrategia(moeda):
    try:
        # 🛑 Ignorar moedas com pouco volume (ex: < 500.000 USDT nas últimas 24h)
        ticker = exchange.fetch_ticker(moeda)
        if ticker['quoteVolume'] < 500_000:
            return  # ignora moeda com volume baixo

        # 📈 Obter candles
        candles = exchange.fetch_ohlcv(moeda, timeframe=TIMEFRAME, limit=100)
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # 🧠 Indicadores técnicos
        df['RSI'] = RSIIndicator(close=df['close'], window=14).rsi()
        df['SMA'] = SMAIndicator(close=df['close'], window=14).sma_indicator()
        df['EMA'] = EMAIndicator(close=df['close'], window=14).ema_indicator()
        df['volume_medio'] = df['volume'].rolling(window=14).mean()

        macd = MACD(close=df['close'])
        df['MACD'] = macd.macd()
        df['MACD_signal'] = macd.macd_signal()

        bb = BollingerBands(close=df['close'], window=20, window_dev=2)
        df['BB_upper'] = bb.bollinger_hband()
        df['BB_lower'] = bb.bollinger_lband()

        # 🔍 Últimos valores
        preco = df['close'].iloc[-1]
        rsi = df['RSI'].iloc[-1]
        sma = df['SMA'].iloc[-1]
        ema = df['EMA'].iloc[-1]
        vol = df['volume'].iloc[-1]
        vol_med = df['volume_medio'].iloc[-1]
        macd_val = df['MACD'].iloc[-1]
        macd_sig = df['MACD_signal'].iloc[-1]
        bb_sup = df['BB_upper'].iloc[-1]
        bb_inf = df['BB_lower'].iloc[-1]

        sinais_compra = 0
        sinais_venda = 0

        # 🧠 Estratégia
        if rsi < 30: sinais_compra += 1
        elif rsi > 70: sinais_venda += 1

        if preco > ema: sinais_compra += 1
        elif preco < ema: sinais_venda += 1

        if preco > sma: sinais_compra += 1
        elif preco < sma: sinais_venda += 1

        if macd_val > macd_sig: sinais_compra += 1
        elif macd_val < macd_sig: sinais_venda += 1

        if preco < bb_inf: sinais_compra += 1
        elif preco > bb_sup: sinais_venda += 1

        if vol > vol_med:
            sinais_compra += 1
            sinais_venda += 1

        total_sinais = max(sinais_compra, sinais_venda)

        # ⚠️ Só enviar alerta se 4 ou mais sinais confirmarem
        if total_sinais >= 4:
            direcao = "ENTRADA" if sinais_compra > sinais_venda else "SAÍDA"

            mensagem = (
                f"📢 Estratégia Detetada - {moeda}\n"
                f"💰 Preço: {preco:.2f} USDT\n"
                f"📊 RSI: {rsi:.2f} | EMA: {ema:.2f} | SMA: {sma:.2f}\n"
                f"📈 MACD: {macd_val:.2f} / sinal: {macd_sig:.2f}\n"
                f"📉 Volume: {vol:.2f} (média: {vol_med:.2f})\n"
                f"🎯 Bollinger: [{bb_inf:.2f} ~ {bb_sup:.2f}]\n"
                f"✅ Sinais de {'compra' if direcao == 'ENTRADA' else 'venda'}: {total_sinais}/6\n"
                f"⚠️ Recomendação: {direcao}"
            )

            enviar_telegram(mensagem)

            # 📝 Guardar no log
            registar_estrategia(
                moeda, direcao, preco, total_sinais,
                rsi, sma, ema, macd_val, macd_sig, vol, vol_med, bb_inf, bb_sup
            )

    except Exception as e:
        print(f"❌ Erro na avaliação de {moeda}: {e}")


# 🌐 Servidor Flask (Render)
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot RSI ativo no Render e pronto a enviar alertas."

# ▶️ Iniciar tudo
if __name__ == "__main__":
    threading.Thread(target=iniciar_bot).start()
    app.run(host="0.0.0.0", port=10000)
