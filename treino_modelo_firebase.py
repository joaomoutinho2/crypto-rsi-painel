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
def carregar_dados_para_treino():
    try:
        docs = db.collection(colecao).stream()
        registos = []
        ignorados = 0

        for doc in docs:
            data = doc.to_dict()

            if not all(k in data for k in campos_necessarios):
                print(f"❌ Faltam campos no doc {doc.id}: {[k for k in campos_necessarios if k not in data]}")
                ignorados += 1
                continue

            if any(v is None or (isinstance(v, float) and pd.isna(v)) for v in [data[k] for k in campos_necessarios]):
                print(f"❌ Valores inválidos no doc {doc.id}: {data}")
                ignorados += 1
                continue

            if data["resultado"] not in [0, 1]:
                print(f"❌ Resultado inválido no doc {doc.id}: {data['resultado']}")
                ignorados += 1
                continue

            registos.append(data)

        if not registos:
            print("❌ Nenhum registo válido encontrado para treino.")
            return None, ignorados

        print(f"📊 {len(registos)} registos válidos carregados.")
        print(f"⚠️ {ignorados} documentos ignorados por dados incompletos ou inválidos.")

        return registos, ignorados

    except Exception as e:
        print(f"❌ Erro ao carregar dados do Firestore: {e}")
        return None, 0

# 🔁 Treino automático externo (para thread_bot)
def treinar_modelo_automaticamente():
    try:
        print("🧠 A treinar modelo automaticamente...")
        registos, ignorados = carregar_dados_para_treino()
        if not registos:
            return None

        df = pd.DataFrame(registos)
        features = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position"]

        if len(df) < 2:
            print("❌ Dados insuficientes para treino.")
            return None

        X = df[features]
        y = df["resultado"]

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

        try:
            joblib.dump(modelo, "modelo_treinado.pkl")
            print("💾 Modelo guardado como modelo_treinado.pkl")
        except Exception as e:
            print(f"❌ Erro ao guardar modelo localmente: {e}")

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

        return modelo

    except Exception as e:
        print(f"❌ Erro no treino automático: {e}")
        return None

# 🔧 Função principal (permite ser usada fora)
def main():
    treinar_modelo_automaticamente()
