import time
from datetime import datetime, timedelta
import os
import csv
import schedule
import logging

from config import RSI_ENTRADA, RSI_SAIDA, LOG_PATH, MOEDAS
from utils import fetch_ohlcv, calcular_rsi
from telegram_alert import enviar_telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.info("Bot iniciado.")

INTERVALO_ALERTA = 7200  # 2 horas
INTERVALO_VERIFICACAO = 300  # 5 minutos

# Dicionário para guardar último alerta enviado por cada par
ultimo_alerta = {}  # { 'BTC/USDT': {'tipo': 'ENTRADA', 'hora': datetime} }

def verificar_rsi(par):
    df = fetch_ohlcv(par)
    if df is None or df.empty:
        print(f"⚠️ Dados de {par} estão vazios ou inválidos.")
        return
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
    passou_tempo = (agora - hora_anterior).total_seconds() > INTERVALO_ALERTA  # 2 horas

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
        mensagem = mensagem[:4093] + "..." if len(mensagem) > 4096 else mensagem
        enviar_telegram(mensagem)

        # Atualizar estado
        ultimo_alerta[par] = {"tipo": alerta, "hora": agora}
    else:
        print(f"🔁 Alerta repetido ({alerta}) e ainda dentro das 2h — ignorado.")

# Criar ficheiro de log se não existir
if not os.path.exists(LOG_PATH):
    try:
        with open(LOG_PATH, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Ativo', 'Preço', 'RSI', 'Alerta'])
    except IOError as e:
        print(f"❌ Erro ao criar arquivo de log: {e}")
        exit(1)

def executar_verificacao():
    for moeda in MOEDAS:
        try:
            verificar_rsi(moeda)
        except ValueError as e:
            print(f"❌ Erro de valor ao verificar {moeda}: {e}")
        except Exception as e:
            print(f"❌ Erro inesperado ao verificar {moeda}: {e}")
        print("-" * 60)

schedule.every(INTERVALO_VERIFICACAO / 60).minutes.do(executar_verificacao)

while True:
    schedule.run_pending()
    time.sleep(1)
