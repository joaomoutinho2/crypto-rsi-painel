import ccxt
import pandas as pd
from datetime import datetime
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands

def executar_backtest(moeda, data_inicio, data_fim, timeframe="1h", lucro_objetivo=0.10, perda_maxima=-0.05):
    print(f"📈 {moeda} | {data_inicio} → {data_fim}")
    exchange = ccxt.kucoin()
    exchange.load_markets()

    since = int(pd.to_datetime(data_inicio).timestamp() * 1000)
    ate = int(pd.to_datetime(data_fim).timestamp() * 1000)
    candles = exchange.fetch_ohlcv(moeda, timeframe=timeframe, since=since, limit=1000)

    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df[df["timestamp"] <= pd.to_datetime(data_fim)]

    if len(df) < 50:
        print("⚠️ Poucos dados.")
        return pd.DataFrame()

    df["RSI"] = RSIIndicator(close=df["close"]).rsi()
    df["EMA"] = EMAIndicator(close=df["close"]).ema_indicator()
    macd = MACD(close=df["close"])
    df["MACD"] = macd.macd()
    df["MACD_signal"] = macd.macd_signal()
    df["volume_medio"] = df["volume"].rolling(window=14).mean()
    bb = BollingerBands(close=df["close"])
    df["BB_lower"] = bb.bollinger_lband()
    df["BB_upper"] = bb.bollinger_hband()

    resultados = []
    em_posicao = False
    entrada = 0
    data_entrada = None
    info_entrada = {}

    for i in range(50, len(df)):
        if not em_posicao:
            sinais = 0
            if df["RSI"].iloc[i] < 30: sinais += 1
            if df["close"].iloc[i] < df["BB_lower"].iloc[i]: sinais += 1
            if df["close"].iloc[i] > df["EMA"].iloc[i]: sinais += 1
            if df["MACD"].iloc[i] > df["MACD_signal"].iloc[i]: sinais += 1
            if df["volume"].iloc[i] > df["volume_medio"].iloc[i]: sinais += 1

            if sinais >= 3:
                entrada = df["close"].iloc[i]
                data_entrada = df["timestamp"].iloc[i]
                info_entrada = {
                    "RSI": df["RSI"].iloc[i],
                    "EMA_diff": (df["close"].iloc[i] - df["EMA"].iloc[i]) / df["EMA"].iloc[i],
                    "MACD_diff": df["MACD"].iloc[i] - df["MACD_signal"].iloc[i],
                    "Volume_relativo": df["volume"].iloc[i] / df["volume_medio"].iloc[i],
                    "BB_position": (df["close"].iloc[i] - df["BB_lower"].iloc[i]) / (df["BB_upper"].iloc[i] - df["BB_lower"].iloc[i])
                }
                em_posicao = True
        else:
            preco_atual = df["close"].iloc[i]
            lucro = (preco_atual - entrada) / entrada
            if lucro >= lucro_objetivo or lucro <= perda_maxima:
                resultados.append({
                    "Moeda": moeda,
                    "Data Entrada": data_entrada,
                    "Data Saída": df["timestamp"].iloc[i],
                    "Entrada": entrada,
                    "Saída": preco_atual,
                    "Lucro (%)": round(lucro * 100, 2),
                    **info_entrada
                })
                em_posicao = False

    return pd.DataFrame(resultados)
