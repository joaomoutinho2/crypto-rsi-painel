"""
🤖 Script de Treino e Avaliação de Modelo de Previsão

Este ficheiro serve para treinar um modelo com dados do Firestore e avaliar os seus resultados.
Utiliza o módulo treino_modelo_firebase.py e imprime métricas de desempenho.
"""

import joblib
from treino_modelo_firebase import modelo as modelo_treinado
from sklearn.metrics import mean_absolute_error, mean_squared_error
from firebase_config import iniciar_firebase
import pandas as pd

# Inicializar Firebase (opcional se já estiver no treino)
db = iniciar_firebase()

# 📊 Função para avaliar previsões de teste

def avaliar_resultados(y_verdadeiro, y_previsto):
    mae = mean_absolute_error(y_verdadeiro, y_previsto)
    mse = mean_squared_error(y_verdadeiro, y_previsto)
    print(f"\n📉 Avaliação do Modelo:")
    print(f"MAE: {mae:.4f}")
    print(f"MSE: {mse:.4f}")

# 🚀 Função principal

def main():
    print("\n🚀 Avaliação do modelo iniciado...")
    if modelo_treinado is None:
        print("❌ Modelo não encontrado. Certifica-te que foi treinado antes.")
        return

    # Exemplo de dados de teste
    dados_teste = pd.DataFrame([
        {"RSI": 30, "EMA_diff": -10, "MACD_diff": -1, "Volume_relativo": 1200, "BB_position": 0.1},
        {"RSI": 70, "EMA_diff": 12, "MACD_diff": 2, "Volume_relativo": 800, "BB_position": 0.9},
    ])
    y_real = [0, 1]  # valores reais esperados para comparação

    previsoes = modelo_treinado.predict(dados_teste)
    avaliar_resultados(y_real, previsoes)

if __name__ == "__main__":
    main()
