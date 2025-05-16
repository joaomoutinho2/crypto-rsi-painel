"""
📈 Treino de Modelo com Dados do Firestore

Este módulo carrega dados da coleção 'historico_previsoes', treina um modelo de regressão
(RandomForestRegressor) e guarda o modelo serializado em base64, juntamente com o registo
do treino na coleção 'modelos_treinados'.
"""

import pandas as pd
import numpy as np
import joblib
import base64
from io import BytesIO
from datetime import datetime
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error

from firebase_config import iniciar_firebase

db = iniciar_firebase()

# 🎯 Carregar dados do Firestore

def carregar_dados_treino():
    docs = db.collection("historico_previsoes").stream()
    dados = [doc.to_dict() for doc in docs if isinstance(doc.to_dict().get("resultado"), (int, float))]
    df = pd.DataFrame(dados)

    campos = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position", "resultado"]
    if not all(c in df.columns for c in campos):
        print("❌ Dados incompletos para treino.")
        return None

    df.dropna(inplace=True)
    return df[campos]

# 🤖 Treinar modelo e guardar no Firestore

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

    buffer = BytesIO()
    joblib.dump(modelo, buffer)
    modelo_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    db.collection("modelos_treinados").add({
        "data": datetime.utcnow(),
        "mse": mse,
        "mae": mae,
        "modelo": modelo_b64,
        "n_registos": len(df)
    })

    print(f"✅ Modelo treinado e guardado | Registos: {len(df)} | MAE: {mae:.4f} | MSE: {mse:.4f}")
    return modelo

# 🔁 Execução automática

def treinar_modelo_automaticamente():
    print("\n🤖 Iniciando treino do modelo...")
    return treinar_modelo_e_guardar()

# Exporta o último modelo treinado automaticamente se importado
modelo = treinar_modelo_automaticamente()
