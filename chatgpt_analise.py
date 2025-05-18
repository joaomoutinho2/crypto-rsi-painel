import os
from openai import OpenAI

# ✅ Cliente OpenAI moderno
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def avaliar_com_chatgpt(simbolo, rsi, macd, volume, objetivo):
    prompt = (
        f"A moeda {simbolo} tem os seguintes indicadores técnicos:\n"
        f"- RSI: {rsi:.2f}\n"
        f"- MACD: {macd:.2f}\n"
        f"- Volume: {volume:.2f}\n"
        f"- Objetivo de lucro: {objetivo:.2f}%\n\n"
        f"O modelo previu uma entrada. Com base nestes dados, esta entrada parece justificada?\n"
        f"Responde de forma curta, técnica e clara."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "És um analista técnico de criptomoedas."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Erro ao consultar ChatGPT: {e}"
