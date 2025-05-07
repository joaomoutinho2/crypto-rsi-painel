import time
from datetime import datetime, timedelta
import os
import csv

from config import RSI_ENTRADA, RSI_SAIDA, LOG_PATH, MOEDAS
from utils import fetch_ohlcv, calcular_rsi
from telegram_alert import enviar_telegram

# Dicionário para guardar último alerta enviado por cada par
ultimo_alerta = {}  # { 'BTC/USDT': {'tipo': 'ENTRADA', 'hora': datetime} }

def verificar_rsi(par):
    df = fetch_ohlcv(par)
    df = calcular_rsi(df)

    rsi_atual = df['RSI'].iloc[-1]
    preco_atual = df['close'].iloc[-1]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    agora = datetime.now()

    print(f"\n[{timestamp}] {par} | Preço: {preco_atual:.2f} USDT | RSI: {rsi_atual:.2f}")

    if rsi_atual < RSI_ENTRADA:
        alerta = "ENTRADA"
        print("🔔 RSI em sobrevenda (Entrada sugerida)")
    elif rsi_atual > RSI_SAIDA:
        alerta = "SAÍDA"
        print("🔔 RSI em sobrecompra (Saída sugerida)")
    else:
        alerta = "NEUTRO"
        print("ℹ️ RSI em zona neutra")

    # Recuperar info anterior
    info_anterior = ultimo_alerta.get(par, {})
    tipo_anterior = info_anterior.get("tipo")
    hora_anterior = info_anterior.get("hora", agora - timedelta(hours=999))
    passou_tempo = (agora - hora_anterior).total_seconds() > 7200  # 2 horas

    if alerta != tipo_anterior or passou_tempo:
        # Guardar no CSV
        with open(LOG_PATH, mode='a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, par, preco_atual, rsi_atual, alerta])

        # Enviar para Telegram
        mensagem = (
            f"⏰ {timestamp}\n"
            f"📈 Ativo: {par}\n"
            f"💰 Preço: {preco_atual:.2f} USDT\n"
            f"📊 RSI: {rsi_atual:.2f}\n"
            f"⚠️ Alerta: {alerta}"
        )
        enviar_telegram(mensagem)

        # Atualizar estado
        ultimo_alerta[par] = {"tipo": alerta, "hora": agora}
    else:
        print(f"🔁 Alerta repetido ({alerta}) e ainda dentro das 2h — ignorado.")

# Criar ficheiro de log se não existir
if not os.path.exists(LOG_PATH):
    with open(LOG_PATH, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Timestamp', 'Ativo', 'Preço', 'RSI', 'Alerta'])

# Loop principal
while True:
    for moeda in MOEDAS:
        try:
            verificar_rsi(moeda)
        except Exception as e:
            print(f"❌ Erro ao verificar {moeda}: {e}")
        print("-" * 60)
    time.sleep(300)  # Espera 5 minutos
