import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import joblib
from firebase_config import iniciar_firebase
from datetime import datetime, timedelta

# 🔥 Inicializar Firestore
try:
    db = iniciar_firebase()
except Exception as e:
    print(f"❌ Erro ao inicializar Firestore: {e}")
    exit()

# 📂 Nome da coleção a corrigir
colecao = "historico_previsoes"

# 🔁 Atualizar documentos que não tenham o campo 'resultado'
try:
    docs = db.collection(colecao).get()
    total = 0
    atualizados = 0

    for doc in docs:
        total += 1
        data = doc.to_dict()
        doc_ref = doc.reference

        if "resultado" not in data:
            print(f"🛠️ Atualizando {doc.id} - campo 'resultado' adicionado com valor 'pendente'")
            doc_ref.update({"resultado": "pendente"})
            atualizados += 1

    print(f"\n📊 {total} documentos verificados.")
    print(f"✅ {atualizados} documentos atualizados com 'resultado: pendente'.")

except Exception as e:
    print(f"❌ Erro ao processar documentos: {e}")
    exit()

# 📅 Ler dados reais do Firebase
try:
    docs = db.collection(colecao).stream()
    registos = []
    campos_necessarios = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position", "resultado"]

    for doc in docs:
        data = doc.to_dict()

        # Verificar se todos os campos necessários estão presentes
        if not all(k in data for k in campos_necessarios):
            print(f"⚠️ Documento ignorado: {doc.id} - Faltam campos necessários")
            continue

        # Verificar se os valores dos campos são válidos (não None ou NaN)
        if any(v is None or (isinstance(v, float) and pd.isna(v)) for v in [data[k] for k in campos_necessarios]):
            print(f"⚠️ Documento ignorado: {doc.id} - Contém valores inválidos")
            continue

        # Verificar se o campo resultado é 0 ou 1 (ignorar 'pendente')
        if data["resultado"] not in [0, 1]:
            print(f"⚠️ Documento ignorado: {doc.id} - resultado inválido: {data['resultado']}")
            continue

        registos.append(data)

    if not registos:
        print("❌ Nenhum registo válido encontrado no Firestore.")
        exit()

    print(f"📊 {len(registos)} registos carregados do Firestore para treino.")

except Exception as e:
    print(f"❌ Erro ao carregar dados do Firestore: {e}")
    exit()

# 🔢 Criar DataFrame
df = pd.DataFrame(registos)
features = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position"]

if not all(f in df.columns for f in features):
    print(f"❌ Faltam colunas obrigatórias nos dados: {features}")
    exit()

X = df[features]
y = df["resultado"]

if len(df) < 2:
    print("❌ Ainda não há dados suficientes no Firestore para treino.")
    exit()

# 🔀 Dividir dados em treino e teste
try:
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
except Exception as e:
    print(f"❌ Erro ao dividir os dados em treino e teste: {e}")
    exit()

# 🤖 Treinar o modelo
try:
    modelo = RandomForestClassifier(n_estimators=100, random_state=42)
    modelo.fit(X_train, y_train)
except Exception as e:
    print(f"❌ Erro ao treinar o modelo: {e}")
    exit()

# 📊 Avaliar o modelo
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

# 💾 Guardar modelo
try:
    joblib.dump(modelo, "modelo_treinado.pkl")
    print("✅ Modelo guardado como modelo_treinado.pkl")
except Exception as e:
    print(f"❌ Erro ao guardar o modelo localmente: {e}")
    exit()

# ☁️ Guardar metadados do modelo no Firestore
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
    print("📤 Resultados do modelo guardados em Firestore (coleção modelos_treinados).")
except Exception as e:
    print(f"❌ Erro ao guardar resultado no Firestore: {e}")

def treinar_modelo_automaticamente():
    from treino_modelo_firebase import main
    try:
        print("🧠 A treinar modelo automaticamente...")
        main()
    except Exception as e:
        print(f"❌ Erro no treino automático: {e}")
