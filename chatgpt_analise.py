import openai
import os

# Lê a API key do ambiente
openai.api_key = os.getenv("OPENAI_API_KEY")

# Função de avaliação com linguagem natural

def avaliar_com_chatgpt(simbolo, rsi, macd, volume, objetivo):
    prompt = (
        f"A moeda {simbolo} tem os seguintes indicadores técnicos:\n"
        f"- RSI: {rsi:.2f}\n"
        f"- MACD: {macd:.2f}\n"
        f"- Volume: {volume:.2f}\n"
        f"- Objetivo de lucro: {objetivo:.2f}%\n\n"
        f"O modelo previu uma entrada. Com base nestes dados, esta entrada parece justificada?"
        f" Dá uma resposta curta, técnica e objetiva."
    )

    try:
        resposta = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "És um assistente de análise técnica especializado em criptomoedas."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_tokens=150
        )
        return resposta.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Erro ao consultar ChatGPT: {e}"
