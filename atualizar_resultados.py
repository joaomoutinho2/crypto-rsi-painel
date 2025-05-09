from firebase_config import iniciar_firebase
from datetime import datetime
import ccxt

EXCHANGE = ccxt.kucoin()
db = iniciar_firebase()

def atualizar_resultados_firestore():
    docs = db.collection("historico_previsoes").where("resultado", "==", None).stream()

    for doc in docs:
        data = doc.to_dict()
        try:
            moeda = data["moeda"]
            ema_diff = float(data.get("EMA_diff", 0))
            data_entrada = data["data"].replace(tzinfo=None)

            ticker = EXCHANGE.fetch_ticker(moeda)
            preco_atual = ticker["last"]

            preco_entrada_estimado = max(preco_atual / (1 + ema_diff), 0.0001)
            variacao = (preco_atual - preco_entrada_estimado) / preco_entrada_estimado * 100
            resultado = 1 if variacao >= 2 else 0

            doc.reference.update({
                "preco_atual": preco_atual,
                "variacao": variacao,
                "resultado": resultado
            })

            print(f"✅ Atualizado {moeda} com resultado {resultado} ({variacao:.2f}%)")

        except Exception as e:
            print(f"⚠️ Erro em {data.get('moeda', '???')}: {e}")

if __name__ == "__main__":
    atualizar_resultados_firestore()
