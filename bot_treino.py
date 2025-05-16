
import os
import time
import gc
from datetime import datetime, timedelta
import ccxt
from firebase_config import iniciar_firebase
from treino_modelo_firebase import treinar_modelo_automaticamente

db = iniciar_firebase()

def avaliar_resultados(exchange, limite=50):
    try:
        colecao = db.collection("historico_previsoes")
        docs = list(colecao.limit(limite).stream())
        atualizados = 0
        ignorados = 0
        erros = 0
        for doc in docs:
            data = doc.to_dict()
            doc_id = doc.id
            if data.get("resultado") not in [None, "pendente", "null", ""]:
                continue
            avaliado_em_str = data.get("avaliado_em")
            if avaliado_em_str:
                try:
                    avaliado_em = datetime.strptime(avaliado_em_str, "%Y-%m-%d %H:%M:%S")
                    if datetime.now() - avaliado_em < timedelta(hours=24):
                        continue
                except Exception:
                    pass
            moeda = data.get("Moeda")
            preco_entrada = data.get("preco_entrada")
            if not moeda or preco_entrada is None:
                ignorados += 1
                continue
            try:
                ticker = exchange.fetch_ticker(moeda)
                preco_atual = ticker["last"]
                resultado_pct = round((preco_atual - preco_entrada) / preco_entrada * 100, 2)
                db.collection("historico_previsoes").document(doc_id).update({
                    "resultado": resultado_pct,
                    "avaliado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                atualizados += 1
            except Exception as e:
                erros += 1
                print(f"⚠️ Erro em {moeda}: {e}")
        print(f"✅ Avaliação: {atualizados} atualizados, {ignorados} ignorados, {erros} erros.")
    except Exception as e:
        print(f"❌ Erro geral na avaliação: {e}")

def main():
    print("🧠 A treinar modelo com dados do Firestore...")
    modelo = treinar_modelo_automaticamente()
    print("✅ Modelo treinado com sucesso.")
    print("📊 A avaliar previsões pendentes...")
    exchange = ccxt.kucoin({"enableRateLimit": True})
    exchange.load_markets()
    avaliar_resultados(exchange)
    gc.collect()

if __name__ == "__main__":
    main()
