"""
🔁 Atualização de Resultados no Firestore

Este script varre a coleção 'historico_previsoes' e preenche o campo 'resultado'
com base na previsão do modelo, sempre que o campo estiver definido como 'pendente'.
"""

from firebase_config import iniciar_firebase
from treino_modelo_firebase import modelo
import pandas as pd

# Inicializar Firestore
db = iniciar_firebase()

# 🛠️ Atualizar previsões pendentes no Firestore
def atualizar_resultados_firestore():
    """
    Atualiza documentos em 'historico_previsoes' com resultado pendente.
    Usa o modelo carregado para prever com base nos campos técnicos.
    """
    try:
        docs = db.collection("historico_previsoes").where("resultado", "==", "pendente").stream()
        total = 0
        atualizados = 0

        for doc in docs:
            data = doc.to_dict()
            total += 1
            campos = ["RSI", "EMA_diff", "MACD_diff", "Volume_relativo", "BB_position"]
            if all(c in data for c in campos):
                entrada = pd.DataFrame([data])[campos]
                pred = modelo.predict(entrada)[0]
                db.document(doc.reference.path).update({"resultado": float(pred)})
                atualizados += 1

        print(f"✅ Atualizados: {atualizados} de {total} documentos pendentes.")

    except Exception as e:
        print(f"❌ Erro na atualização de resultados: {e}")
