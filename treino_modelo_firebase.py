import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
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

            # Validar campos
            if not all(k in data for k in campos_necessarios):
                ignorados += 1
                continue
            if any(v is None or (isinstance(v, float) and pd.isna(v)) for v in [data[k] for k in campos_necessarios]):
                ignorados += 1
                continue
            if data["resultado"] not in [0, 1]:
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
        modelo = RandomForestClassifier(n_estimators=100, random_state=42)
        modelo.fit(X_train, y_train)

        y_pred = modelo.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        relatorio = classification_report(y_test, y_pred, output_dict=True)
        matriz = confusion_matrix(y_test, y_pred).tolist()

        print(f"✅ Modelo treinado com acurácia: {acc:.4f}")

        # 💾 Serializar modelo para base64
        buffer = io.BytesIO()
        joblib.dump(modelo, buffer)
        modelo_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        # ☁️ Guardar no Firestore
        resultado_doc = {
            "data_treino": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "features": features,
            "modelo": "RandomForestClassifier",
            "acuracia": acc,
            "relatorio": relatorio,
            "matriz_confusao": matriz,
            "modelo_serializado": modelo_base64,
            "resultado": "treinado"
        }
        db.collection("modelos_treinados").add(resultado_doc)
        print("📤 Resultados do modelo guardados em Firestore com modelo serializado.")

    except Exception as e:
        print(f"❌ Erro ao treinar ou guardar modelo: {e}")

# 🔁 Treino automático externo (para thread_bot)
def treinar_modelo_automaticamente():
    try:
        print("🧠 A treinar modelo automaticamente...")
        treinar_modelo_e_guardar()
    except Exception as e:
        print(f"❌ Erro no treino automático: {e}")

# 🔧 Função principal para testes manuais
if __name__ == "__main__":
    treinar_modelo_e_guardar()
