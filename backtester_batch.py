
import pandas as pd
from backtester_com_indicadores import executar_backtest

# ⚙️ Configurações de datas e moedas
periodos = [
    ("2025-03-01 00:00:00", "2025-04-01 00:00:00"),
    ("2025-04-01 00:00:00", "2025-05-01 00:00:00"),
    ("2025-04-05 00:00:00", "2025-04-12 00:00:00"),
    ("2025-05-01 00:00:00", "2025-05-08 00:00:00")
]

moedas = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]

# 🔁 Executar combinações e guardar em CSVs
for moeda in moedas:
    for data_inicio, data_fim in periodos:
        print(f"⏳ Backtest: {moeda} de {data_inicio} até {data_fim}")
        df = executar_backtest(moeda=moeda, data_inicio=data_inicio, data_fim=data_fim)
        if not df.empty:
            nome = f"resultados_{moeda.split('/')[0].lower()}_{data_inicio[:10]}.csv".replace("-", "")
            df.to_csv(nome, index=False)
            print(f"✅ Guardado: {nome}")
        else:
            print("⚠️ Sem resultados.")
