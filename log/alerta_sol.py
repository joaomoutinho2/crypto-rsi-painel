import ccxt
import pandas as pd
from ta.momentum import RSIIndicator
import time

# Ligação à Binance
exchange = ccxt.binance()

# Função para obter dados de preço (1 hora)
def fetch_ohlcv():
    candles = exchange.fetch_ohlcv('SOL/USDT', timeframe='1h', limit=100)
    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    return df

# Função para calcular RSI e mostrar alerta
def verificar_rsi():
    df = fetch_ohlcv()
    rsi = RSIIndicator(close=df['close'], window=14)
    df['RSI'] = rsi.rsi()
    rsi_atual = df['RSI'].iloc[-1]
    preco_atual = df['close'].iloc[-1]

    print(f"\nPreço atual: {preco_atual:.2f} USDT | RSI: {rsi_atual:.2f}")

    if rsi_atual < 30:
        print("🔔 ENTRADA SUGERIDA: RSI < 30 (Sobrevenda)")
    elif rsi_atual > 70:
        print("🔔 SAÍDA SUGERIDA: RSI > 70 (Sobrecompra)")
    else:
        print("ℹ️ RSI em zona neutra.")

# Executar a cada 5 minutos
while True:
    verificar_rsi()
    print("-" * 50)
    time.sleep(300)  # 300 segundos = 5 minutos
