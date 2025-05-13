import ccxt
import pandas as pd
from ta.momentum import RSIIndicator
from config import TIMEFRAME, EXCHANGE

# Criar ligação à exchange dinamicamente
def get_exchange():
    try:
        exchange_class = getattr(ccxt, EXCHANGE)
        return exchange_class()
    except AttributeError:
        raise Exception(f"Exchange '{EXCHANGE}' não é suportada pelo ccxt.")

exchange = get_exchange()

def fetch_ohlcv(par, timeframe='1h'):
    candles = exchange.fetch_ohlcv(par, timeframe=timeframe, limit=100)
    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    return df

def calcular_rsi(df):
    rsi = RSIIndicator(close=df['close'], window=14)
    df['RSI'] = rsi.rsi()
    return df
