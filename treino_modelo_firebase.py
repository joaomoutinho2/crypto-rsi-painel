import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import joblib
from firebase_config import iniciar_firebase
from datetime import datetime

# 🔥 Inicializar Firestore
try:
    db = iniciar_firebase()
except Exception as e:
    print(f"❌ Erro ao inicializar Firestore: {e}")
    exit()

colecao = "historico_previsoes"
campos_necessarios = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position", "resultado"]

# 🔁 Atualizar documentos sem campo 'resultado'
try:
    docs = db.collection(colecao).get()
    total = len(docs)
    atualizados = 0

    for doc in docs:
        if "resultado" not in doc.to_dict():
            doc.reference.update({"resultado": "pendente"})
            atualizados += 1

    print(f"🛠️ {atualizados} documentos atualizados com 'resultado: pendente' (de {total}).")

except Exception as e:
    print(f"❌ Erro ao atualizar documentos: {e}")
    exit()

# 📥 Carregar dados válidos para treino
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
        exit()

    print(f"📊 {len(registos)} registos válidos carregados.")
    print(f"⚠️ {ignorados} documentos ignorados por dados incompletos ou inválidos.")

except Exception as e:
    print(f"❌ Erro ao carregar dados do Firestore: {e}")
    exit()

# 🔢 Treinar modelo
df = pd.DataFrame(registos)
features = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position"]

if len(df) < 2:
    print("❌ Dados insuficientes para treino.")
    exit()

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
    print("📊 Matriz de Confusão:")
    print(confusion_matrix(y_test, y_pred))

except Exception as e:
    print(f"❌ Erro ao treinar ou avaliar o modelo: {e}")
    exit()

# 💾 Guardar modelo localmente
try:
    joblib.dump(modelo, "modelo_treinado.pkl")
    print("💾 Modelo guardado como modelo_treinado.pkl")
except Exception as e:
    print(f"❌ Erro ao guardar modelo localmente: {e}")
    exit()

# ☁️ Guardar resultados no Firestore
try:
    resultado_doc = {
        "data_treino": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "features": features,
        "modelo": "RandomForestClassifier",
        "acuracia": acc,
        "relatorio": relatorio,
        "matriz_confusao": matriz,
        "resultado": "treinado"
    }
    db.collection("modelos_treinados").add(resultado_doc)
    print("📤 Resultados do modelo guardados em Firestore.")

except Exception as e:
    print(f"❌ Erro ao guardar resultados no Firestore: {e}")

# 🔁 Treino automático externo (para thread_bot)
def treinar_modelo_automaticamente():
    try:
        print("🧠 A treinar modelo automaticamente...")
        main()
    except Exception as e:
        print(f"❌ Erro no treino automático: {e}")

# 🔧 Função principal (permite ser usada fora)
def main():
    # Tudo já correu acima automaticamente
    pass
