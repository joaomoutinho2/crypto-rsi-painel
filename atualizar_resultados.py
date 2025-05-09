from firebase_config import iniciar_firebase
from datetime import datetime
import ccxt

EXCHANGE = ccxt.kucoin()
db = iniciar_firebase()

def atualizar_resultados_firestore():
    docs = db.collection("historico_previsoes").where("resultado", "==", None).stream()
    contador = 0

    for doc in docs:
        data = doc.to_dict()
        try:
            moeda = data.get("moeda")
            ema_diff = float(data.get("EMA_diff", 0))
            data_entrada = data.get("data")

            if data_entrada is None or not moeda:
                continue

            # Converter datetime para formato correto se vier do Firestore
            if hasattr(data_entrada, 'replace'):
                data_entrada = data_entrada.replace(tzinfo=None)

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
            contador += 1

        except Exception as e:
            print(f"⚠️ Erro em {data.get('moeda', '???')}: {e}")

    print(f"\n🟢 {contador} previsões atualizadas com sucesso.")

if __name__ == "__main__":
    atualizar_resultados_firestore()
