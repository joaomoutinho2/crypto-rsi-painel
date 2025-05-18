import os
import pandas as pd
from time import sleep
from random import uniform, seed
from datetime import datetime
from firebase_config import iniciar_firebase
from openai import OpenAI
from uuid import uuid4


# 🔐 API Key
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 🔁 Função para gerar linha de entrada

def gerar_linha():
    return {
        "RSI": round(uniform(10, 90), 2),
        "MACD_diff": round(uniform(-5, 5), 2),
        "Volume_relativo": round(uniform(0.2, 5.0), 2),
        "BB_position": round(uniform(0, 1), 2),
        "EMA_diff": round(uniform(-3, 3), 2)
    }

# 🤖 Função para obter decisão do ChatGPT

def avaliar_linha_chatgpt(linha):
    prompt = (
        f"Tenho os seguintes indicadores:\n"
        f"- RSI: {linha['RSI']}\n"
        f"- MACD_diff: {linha['MACD_diff']}\n"
        f"- Volume_relativo: {linha['Volume_relativo']}\n"
        f"- BB_position: {linha['BB_position']}\n"
        f"- EMA_diff: {linha['EMA_diff']}\n"
        "Isto é uma boa entrada (1) ou não (0)? Só responde com 1 ou 0."
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "És um analista técnico de criptomoedas."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=3
        )

        saida = response.choices[0].message.content.strip()
        return int(saida) if saida in ["0", "1"] else None
    except Exception as e:
        print(f"❌ Erro ao consultar GPT: {e}")
        return None

# 🔥 Inicializar Firestore
db = iniciar_firebase()

# 🚀 Gerar e injetar 100 entradas
seed(42)
injetados = 0

for i in range(10):
    entrada = gerar_linha()
    resultado = avaliar_linha_chatgpt(entrada)
    if resultado is not None:
        doc = {
            **entrada,
            "resultado": resultado,
            "simbolo": "GPT_SIMULADO",
            "timestamp": datetime.utcnow(),
            "uid": str(uuid4())
        }
        doc_id = str(uuid4())  # ID único garantido
        db.collection("historico_previsoes").document(doc_id).set(doc)
        injetados += 1
        print(f"{i+1:03d} ✔️ RSI={entrada['RSI']} → resultado: {resultado}")
    else:
        print(f"{i+1:03d} ❌ Erro ao avaliar entrada")

print(f"✅ {injetados} entradas geradas e enviadas para o Firestore.")
