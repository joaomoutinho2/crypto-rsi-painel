"""
🤖 Treino Automático de Modelo de Machine Learning com Firestore

Este bot é executado por cron job (ex: no Render) e tem como funções:
- Carregar dados reais da coleção 'historico_previsoes'
- Treinar um modelo de regressão (RandomForest)
- Avaliar o desempenho com MAE, MSE e R²
- Guardar o modelo treinado localmente (modelo_treinado.pkl)
- Codificar o modelo e guardar no Firestore na coleção 'modelos_treinados'
"""

import pandas as pd
import numpy as np
import joblib
import base64
from io import BytesIO
from datetime import datetime
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

from firebase_config import iniciar_firebase

# ✅ Inicializar Firestore
db = iniciar_firebase()

# 📥 Carregar dados reais para treino
def carregar_dados_treino():
    docs = db.collection("historico_previsoes").stream()
    dados = [doc.to_dict() for doc in docs if isinstance(doc.to_dict().get("resultado"), (int, float))]
    df = pd.DataFrame(dados)
    campos = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position", "resultado"]
    if not all(c in df.columns for c in campos):
        print("❌ Dados incompletos.")
        return None
    df.dropna(inplace=True)
    return df[campos]

# 🧠 Treinar o modelo e guardar local + Firestore
def treinar_modelo_e_guardar():
    df = carregar_dados_treino()
    if df is None or df.empty:
        print("❌ Nenhum dado válido para treino.")
        return None

    X = df.drop("resultado", axis=1)
    y = df["resultado"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    modelo = RandomForestRegressor(n_estimators=100, random_state=42)
    modelo.fit(X_train, y_train)

    y_pred = modelo.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    # Guardar localmente
    joblib.dump(modelo, "modelo_treinado.pkl")

    # Codificar e guardar no Firestore
    buffer = BytesIO()
    joblib.dump(modelo, buffer)
    modelo_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    db.collection("modelos_treinados").add({
        "data_treino": datetime.utcnow(),
        "mae": mae,
        "mse": mse,
        "r2": r2,
        "modelo": modelo_b64,
        "n_amostras": len(df)
    })

    print(f"✅ Modelo treinado | MAE: {mae:.4f} | MSE: {mse:.4f} | R²: {r2:.4f} | Registos: {len(df)}")
    return modelo

if __name__ == "__main__":
    treinar_modelo_e_guardar()
