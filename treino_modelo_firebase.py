import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import joblib
from datetime import datetime
from firebase_config import iniciar_firebase
from google.cloud.firestore_v1.base_query import FieldFilter

# 🔥 Inicializar Firestore
db = iniciar_firebase()

# 📅 Ler dados reais do Firebase
docs = db.collection("historico_previsoes").where(
    filter=FieldFilter("resultado", "!=", None)
).stream()
registos = [doc.to_dict() for doc in docs if all(k in doc.to_dict() for k in ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position"])]

df = pd.DataFrame(registos)

print(f"📊 {len(df)} registos carregados do Firestore para treino.")

if len(df) < 2:
    print("❌ Ainda não há dados suficientes no Firestore para treino.")
    exit()

# 🎯 Preparar dados
features = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position"]
X = df[features]
y = df["resultado"]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

# 🤖 Treinar modelo
modelo = RandomForestClassifier(n_estimators=100, random_state=42)
modelo.fit(X_train, y_train)

# 📊 Avaliação
y_pred = modelo.predict(X_test)
acc = accuracy_score(y_test, y_pred)
relatorio = classification_report(y_test, y_pred, output_dict=True)
matriz = confusion_matrix(y_test, y_pred).tolist()

print("\n📊 Relatório de Classificação:")
print(classification_report(y_test, y_pred))
print("\n🧱 Matriz de Confusão:")
print(confusion_matrix(y_test, y_pred))

# 📎 Guardar modelo local
joblib.dump(modelo, "modelo_treinado.pkl")
print("✅ Modelo guardado como modelo_treinado.pkl")

# ☕️ Guardar metadados no Firestore
resultado_doc = {
    "data_treino": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "features": features,
    "modelo": "RandomForestClassifier",
    "acuracia": acc,
    "relatorio": relatorio,
    "matriz_confusao": matriz
}

try:
    db.collection("modelos_treinados").add(resultado_doc)
    print("📤 Resultados do modelo guardados em Firestore (coleção modelos_treinados).")
except Exception as e:
    print(f"❌ Erro ao guardar resultado no Firestore: {e}")
