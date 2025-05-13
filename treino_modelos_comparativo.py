import pandas as pd
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
import joblib

# 📥 Carregar dados
df = pd.read_csv("resultados_backtest.csv")
df["Sucesso"] = df["Lucro (%)"] > 0

# 📊 Features e target
features = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position"]
X = df[features]
y = df["Sucesso"]

# 🧪 Separar treino/teste
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

# 🤖 Modelos a testar
modelos = {
    "Random Forest": RandomForestClassifier(n_estimators=100, random_state=42),
    "Logistic Regression": LogisticRegression(max_iter=1000),
    "Gradient Boosting": GradientBoostingClassifier(),
    "SVM": SVC(probability=True)
}

melhor_modelo = None
melhor_score = 0
nome_melhor = None

print("\n📊 Avaliação dos modelos:")
for nome, modelo in modelos.items():
    modelo.fit(X_train, y_train)
    y_pred = modelo.predict(X_test)
    acc = accuracy_score(y_test, y_pred)

    print(f"\n🧠 Modelo: {nome}")
    print(classification_report(y_test, y_pred))
    print("Confusão:", confusion_matrix(y_test, y_pred))

    if acc > melhor_score:
        melhor_modelo = modelo
        melhor_score = acc
        nome_melhor = nome

# 💾 Guardar o melhor modelo
joblib.dump(melhor_modelo, "modelo_treinado.pkl")
print(f"\n✅ Melhor modelo: {nome_melhor} (accuracy: {melhor_score:.2f}) guardado como modelo_treinado.pkl")

# 📈 Importância das features (se disponível)
if hasattr(melhor_modelo, "feature_importances_"):
    importancias = melhor_modelo.feature_importances_
    plt.figure(figsize=(8, 5))
    plt.barh(features, importancias, color='skyblue')
    plt.xlabel("Importância")
    plt.title(f"📊 Importância das Features ({nome_melhor})")
    plt.tight_layout()
    plt.savefig("importancia_features.png")
    print("📸 Gráfico de importância guardado em 'importancia_features.png'")
else:
    print("ℹ️ O modelo não fornece importâncias de features.")
