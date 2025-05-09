
import ccxt
import pandas as pd
from datetime import datetime
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import BollingerBands

# =======================
# PARÂMETROS DO BACKTEST
# =======================
MOEDAS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TIMEFRAME = "1h"
LUCRO_OBJETIVO = 0.10   # 10%
PERDA_MAXIMA = -0.05    # -5%
MAX_NEGOCIOS = 300
PERIODO = 1000

exchange = ccxt.kucoin()

# =======================
# FUNÇÕES DE ESTRATÉGIA
# =======================
def aplicar_estrategia(df):
    df["RSI"] = RSIIndicator(close=df["close"]).rsi()
    df["EMA"] = EMAIndicator(close=df["close"]).ema_indicator()
    macd = MACD(close=df["close"])
    df["MACD"] = macd.macd()
    df["MACD_signal"] = macd.macd_signal()
    df["volume_medio"] = df["volume"].rolling(window=14).mean()
    bb = BollingerBands(close=df["close"])
    df["BB_lower"] = bb.bollinger_lband()
    df["BB_upper"] = bb.bollinger_hband()
    return df

def avaliar_sinais(df, i):
    sinais = 0
    if df["RSI"].iloc[i] < 30: sinais += 1
    if df["close"].iloc[i] < df["BB_lower"].iloc[i]: sinais += 1
    if df["close"].iloc[i] > df["EMA"].iloc[i]: sinais += 1
    if df["MACD"].iloc[i] > df["MACD_signal"].iloc[i]: sinais += 1
    if df["volume"].iloc[i] > df["volume_medio"].iloc[i]: sinais += 1
    return sinais

# =======================
# BACKTESTING
# =======================
resultados = []

for moeda in MOEDAS:
    print(f"🔍 A processar {moeda}...")
    try:
        candles = exchange.fetch_ohlcv(moeda, timeframe=TIMEFRAME, limit=PERIODO)
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = aplicar_estrategia(df)

        em_posicao = False
        entrada = 0
        data_entrada = None
        info_entrada = {}

        for i in range(50, len(df)):
            if not em_posicao:
                sinais = avaliar_sinais(df, i)
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
                if lucro >= LUCRO_OBJETIVO or lucro <= PERDA_MAXIMA:
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

            if len(resultados) >= MAX_NEGOCIOS:
                break

    except Exception as e:
        print(f"⚠️ Erro em {moeda}: {e}")

# =======================
# EXPORTAR RESULTADOS
# =======================
df_resultados = pd.DataFrame(resultados)
if not df_resultados.empty:
    df_resultados.to_csv("resultados_backtest.csv", index=False)
    print("✅ Resultados guardados em resultados_backtest.csv")
else:
    print("⚠️ Nenhum negócio foi executado com esta estratégia.")
