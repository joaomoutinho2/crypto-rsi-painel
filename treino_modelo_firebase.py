import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from firebase_config import iniciar_firebase
from datetime import datetime
import base64
import joblib
import io

# 🔥 Inicializar Firestore
try:
    db = iniciar_firebase()
except Exception as e:
    print(f"❌ Erro ao inicializar Firestore: {e}")
    exit()

colecao = "historico_previsoes"
campos_necessarios = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position", "resultado"]

# 📥 Carregar dados válidos para treino
def carregar_dados_treino():
    try:
        docs = db.collection(colecao).stream()
        registos = []
        ignorados = 0

        for doc in docs:
            data = doc.to_dict()

            if not all(k in data for k in campos_necessarios):
                ignorados += 1
                continue
            if any(v is None or (isinstance(v, float) and pd.isna(v)) for v in [data[k] for k in campos_necessarios]):
                ignorados += 1
                continue
            try:
                float(data["resultado"])
            except:
                ignorados += 1
                continue

            registos.append(data)

        if not registos:
            print("❌ Nenhum registo válido encontrado para treino.")
            return None, 0

        print(f"📊 {len(registos)} registos válidos carregados.")
        print(f"⚠️ {ignorados} documentos ignorados por dados incompletos ou inválidos.")
        return pd.DataFrame(registos), ignorados

    except Exception as e:
        print(f"❌ Erro ao carregar dados do Firestore: {e}")
        return None, 0

# 🎯 Treinar e guardar modelo
def treinar_modelo_e_guardar():
    df, _ = carregar_dados_treino()
    if df is None or len(df) < 2:
        print("❌ Dados insuficientes para treino.")
        return

    features = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position"]
    X = df[features]
    y = df["resultado"]

    try:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
        modelo = RandomForestRegressor(n_estimators=100, random_state=42)
        modelo.fit(X_train, y_train)

        y_pred = modelo.predict(X_test)
        mse = mean_squared_error(y_test, y_pred)
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)

        print(f"✅ Modelo treinado: R²={r2:.4f} | MAE={mae:.4f} | MSE={mse:.4f}")

        # 💾 Serializar modelo
        buffer = io.BytesIO()
        joblib.dump(modelo, buffer)
        modelo_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        # ☁️ Guardar resultados no Firestore
        resultado_doc = {
            "data_treino": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "features": features,
            "modelo": "RandomForestRegressor",
            "mae": mae,
            "mse": mse,
            "r2": r2,
            "modelo_serializado": modelo_base64,
            "tipo_treino": "regressao"
        }
        db.collection("modelos_treinados").add(resultado_doc)
        print("📤 Resultados do modelo guardados em Firestore com sucesso.")

        return modelo

    except Exception as e:
        print(f"❌ Erro ao treinar ou guardar modelo: {e}")

# 🔁 Treino automático externo (para uso no bot)
def treinar_modelo_automaticamente():
    try:
        print("🧠 A treinar modelo automaticamente...")
        return treinar_modelo_e_guardar()
    except Exception as e:
        print(f"❌ Erro no treino automático: {e}")
        return None

# 🔧 Execução manual
if __name__ == "__main__":
    treinar_modelo_e_guardar()
