
import ccxt
import pandas as pd
from datetime import datetime
import os

FICHEIRO = "historico_previsoes.csv"
EXCHANGE = ccxt.kucoin()

def atualizar_resultados():
    if not os.path.exists(FICHEIRO):
        print("❌ Ficheiro historico_previsoes.csv não encontrado.")
        return

    df = pd.read_csv(FICHEIRO)

    if "Resultado" in df.columns:
        df = df[df["Resultado"].isna()]  # Só prever os que ainda não têm resultado

    resultados = []
    for idx, row in df.iterrows():
        try:
            moeda = row["Moeda"]
            data_entrada = datetime.strptime(row["Data"], "%Y-%m-%d %H:%M:%S")

            # Buscar ticker atual da moeda
            ticker = EXCHANGE.fetch_ticker(moeda)
            preco_atual = ticker["last"]

            # Preço de entrada (estimado a partir da EMA ou atual da altura)
            preco_entrada_estimado = row["EMA_diff"] * 1.0 + 1.0  # inversão do cálculo
            preco_entrada_estimado = max(preco_atual / (1 + row["EMA_diff"]), 0.0001)

            variacao = (preco_atual - preco_entrada_estimado) / preco_entrada_estimado * 100
            resultado = 1 if variacao >= 2 else 0  # considera positivo se lucro ≥ 2%

            resultados.append(resultado)
        except Exception as e:
            print(f"Erro em {row['Moeda']}: {e}")
            resultados.append(None)

    df["Resultado"] = resultados
    df.to_csv(FICHEIRO, index=False)
    print("✅ Resultados atualizados com sucesso!")

if __name__ == "__main__":
    atualizar_resultados()
