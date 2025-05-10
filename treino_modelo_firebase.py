import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import joblib
from datetime import datetime
from firebase_config import iniciar_firebase
from google.cloud.firestore_v1.base_query import FieldFilter

# 🔥 Inicializar Firestore
try:
    db = iniciar_firebase()
except Exception as e:
    print(f"❌ Erro ao inicializar o Firestore: {e}")
    exit()

# 📅 Ler dados reais do Firebase
try:
    docs = db.collection("historico_previsoes").where(
        filter=FieldFilter("resultado", "!=", None)
    ).stream()
    registos = [
        doc.to_dict()
        for doc in docs
        if all(k in doc.to_dict() for k in ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position", "resultado"])
    ]
except Exception as e:
    print(f"❌ Erro ao carregar dados do Firestore: {e}")
    exit()

# Verificar se há dados suficientes
if not registos:
    print("❌ Nenhum registo válido encontrado no Firestore.")
    exit()

df = pd.DataFrame(registos)

# Verificar se a coluna "Previsao" existe
if "Previsao" in df.columns:
    df["Previsao"] = df["Previsao"].astype(int)
else:
    print("❌ A coluna 'Previsao' não foi encontrada nos dados do Firestore.")
    exit()

print(f"📊 {len(df)} registos carregados do Firestore para treino.")

if len(df) < 2:
    print("❌ Ainda não há dados suficientes no Firestore para treino.")
    exit()

# 🎯 Preparar dados
features = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position"]
if not all(feature in df.columns for feature in features):
    print(f"❌ Faltam colunas obrigatórias nos dados: {features}")
    exit()

X = df[features]
y = df["resultado"]

# Dividir os dados em treino e teste
try:
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
except Exception as e:
    print(f"❌ Erro ao dividir os dados em treino e teste: {e}")
    exit()

# 🤖 Treinar modelo
try:
    modelo = RandomForestClassifier(n_estimators=100, random_state=42)
    modelo.fit(X_train, y_train)
except Exception as e:
    print(f"❌ Erro ao treinar o modelo: {e}")
    exit()

# 📊 Avaliação
try:
    y_pred = modelo.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    relatorio = classification_report(y_test, y_pred, output_dict=True)
    matriz = confusion_matrix(y_test, y_pred).tolist()

    print("\n📊 Relatório de Classificação:")
    print(classification_report(y_test, y_pred))
    print("\n🧱 Matriz de Confusão:")
    print(confusion_matrix(y_test, y_pred))
except Exception as e:
    print(f"❌ Erro ao avaliar o modelo: {e}")
    exit()

# 📎 Guardar modelo local
try:
    joblib.dump(modelo, "modelo_treinado.pkl")
    print("✅ Modelo guardado como modelo_treinado.pkl")
except Exception as e:
    print(f"❌ Erro ao guardar o modelo localmente: {e}")
    exit()

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
