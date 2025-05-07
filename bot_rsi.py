import time
import ccxt
import pandas as pd
import requests
import os
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.volatility import BollingerBands

# ⚙️ Configuração (usa variáveis de ambiente no Render)
MOEDAS = ['BTC/USDT', 'ETH/USDT']
TIMEFRAME = '1h'
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# 📩 Enviar mensagem para Telegram
def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
    try:
        response = requests.post(url, data=data)
        if response.status_code != 200:
            print("❌ Erro Telegram:", response.text)
    except Exception as e:
        print("❌ Exceção Telegram:", e)

# 🌐 Ligação à exchange
exchange = ccxt.kucoin()
estado_alertas = {}

# 📊 Lógica de análise para cada moeda
def analisar_moeda(moeda):
    try:
        candles = exchange.fetch_ohlcv(moeda, timeframe=TIMEFRAME, limit=100)
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # Indicadores técnicos
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

        # Sinal principal
        alerta = "NEUTRO"
        if rsi < 30:
            alerta = "ENTRADA"
        elif rsi > 70:
            alerta = "SAÍDA"

        # Enviar alerta se mudar de estado
        if moeda not in estado_alertas or alerta != estado_alertas[moeda]:
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
                f"📈 Alerta RSI - {moeda}\n"
                f"⏱️ Timeframe: {TIMEFRAME}\n"
                f"💰 Preço: {preco:.2f} USDT\n"
                f"📊 RSI: {rsi:.2f} | SMA: {sma:.2f} | EMA: {ema:.2f}\n"
                f"📉 Volume: {vol:.2f} (média: {vol_med:.2f})\n"
                f"📊 MACD: {macd_val:.2f} / sinal: {macd_sig:.2f}\n"
                f"📉 Bollinger: [{bb_inf:.2f} ~ {bb_sup:.2f}]\n"
                f"⚠️ Sinal: {alerta}\n"
                f"{analise}"
            )

            enviar_telegram(mensagem)
            estado_alertas[moeda] = alerta

    except Exception as e:
        print(f"❌ Erro ao processar {moeda}: {e}")

# 🔁 Loop principal
def loop_bot():
    print("✅ Bot RSI iniciado.")
    while True:
        for moeda in MOEDAS:
            analisar_moeda(moeda)
        print("⏳ A aguardar 5 minutos...")
        time.sleep(300)

# 🌐 Microservidor Flask para manter ativo no Render
from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot RSI ativo no Render!"

# ▶️ Executar o bot + servidor Flask em paralelo
if __name__ == "__main__":
    threading.Thread(target=loop_bot).start()
    app.run(host='0.0.0.0', port=10000)
