
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import joblib

# Carregar CSV com indicadores reais
df = pd.read_csv("resultados_backtest.csv")

# Variável alvo: lucro positivo
df["Sucesso"] = df["Lucro (%)"] > 0

# Features com base nos indicadores reais
features = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position"]
X = df[features]
y = df["Sucesso"]

# Separar treino e teste
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

# Treinar modelo
modelo = RandomForestClassifier(n_estimators=100, random_state=42)
modelo.fit(X_train, y_train)

# Avaliação
y_pred = modelo.predict(X_test)
print("📊 Relatório de Classificação:")
print(classification_report(y_test, y_pred))
print("🧱 Matriz de Confusão:")
print(confusion_matrix(y_test, y_pred))

# Guardar modelo treinado
joblib.dump(modelo, "modelo_treinado.pkl")

# Prever um exemplo novo
exemplo = pd.DataFrame([{
    "RSI": 28,
    "EMA_diff": 0.01,
    "MACD_diff": 0.015,
    "Volume_relativo": 1.12,
    "BB_position": 0.2
}])
previsao = modelo.predict(exemplo)[0]
print("\n🔮 Previsão para novo sinal:")
print("✅ Provável de dar lucro" if previsao else "❌ Pouco promissor")
