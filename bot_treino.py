"""
🤖 Treino Automático de Modelo de Machine Learning com Firestore (Avançado)

Este bot:
- Carrega dados reais da coleção 'historico_previsoes'
- Treina um modelo RandomForest com indicadores técnicos
- Guarda o modelo localmente e codificado no Firestore
- Regista métricas como MAE, MSE, R² e taxa de acerto real por moeda
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
    campos = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position", "resultado", "simbolo"]
    if not all(c in df.columns for c in campos):
        print("❌ Dados incompletos.")
        return None
    df.dropna(inplace=True)
    return df[campos]

# 🎯 Avaliar acertos reais por moeda (previsao == resultado)
def calcular_acertos(df):
    if "previsao" not in df.columns:
        return {}
    df_filtrado = df[df["resultado"].isin([0, 1]) & df["previsao"].isin([0, 1])]
    df_filtrado["acertou"] = df_filtrado["previsao"] == df_filtrado["resultado"]
    por_moeda = df_filtrado.groupby("simbolo")["acertou"].mean().sort_values(ascending=False)
    return por_moeda.to_dict()

# 🧠 Treinar o modelo e guardar local + Firestore
def treinar_modelo_e_guardar():
    df = carregar_dados_treino()
    if df is None or df.empty:
        print("❌ Nenhum dado válido para treino.")
        return None

    X = df.drop(["resultado", "simbolo"], axis=1)
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

    # 🔁 Adicionar previsões ao DataFrame de teste
    df_test = X_test.copy()
    df_test["previsao"] = y_pred
    df_test["resultado"] = y_test
    df_test["simbolo"] = df.loc[X_test.index, "simbolo"]

    acertos_por_moeda = calcular_acertos(df_test)

    # 🔐 Codificar modelo e guardar no Firestore
    buffer = BytesIO()
    joblib.dump(modelo, buffer)
    modelo_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    try:
        db.collection("modelos_treinados").add({
            "data_treino": datetime.utcnow(),
            "mae": mae,
            "mse": mse,
            "r2": r2,
            "modelo": modelo_b64,
            "n_amostras": len(df),
            "acertos_por_moeda": acertos_por_moeda
        })
        print("✅ Modelo guardado no Firestore com sucesso.")
    except Exception as e:
        print(f"❌ Erro ao guardar modelo no Firestore: {e}")

    print("📊 Treino concluído")
    print(f"🔹 MAE: {mae:.4f} | MSE: {mse:.4f} | R²: {r2:.4f}")
    print("🏅 Taxa de acerto por moeda:")
    for moeda, taxa in acertos_por_moeda.items():
        print(f" - {moeda}: {taxa:.2%}")

    return modelo

if __name__ == "__main__":
    treinar_modelo_e_guardar()
