
import pandas as pd
import glob
import os

# 🔍 Procurar todos os ficheiros com padrão resultados_*.csv
ficheiros = glob.glob("resultados_*.csv")
print(f"📂 Encontrados: {ficheiros}")

# 📥 Juntar todos
df_total = pd.concat([pd.read_csv(f) for f in ficheiros], ignore_index=True)

# 🧹 Remover duplicados (baseado em todas as colunas)
df_total = df_total.drop_duplicates()

# 💾 Guardar no ficheiro final
df_total.to_csv("resultados_backtest.csv", index=False)
print(f"✅ Ficheiro final criado: resultados_backtest.csv com {len(df_total)} linhas.")
