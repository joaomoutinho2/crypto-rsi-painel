import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import ccxt
import json
import os
from datetime import datetime
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.volatility import BollingerBands
from config import MOEDAS, LOG_PATH
from io import BytesIO
from streamlit_autorefresh import st_autorefresh
from telegram_alert import enviar_telegram

# 📁 Base de dados local
FICHEIRO_POSICOES = "posicoes.json"

def carregar_posicoes():
    if not os.path.exists(FICHEIRO_POSICOES):
        return []
    with open(FICHEIRO_POSICOES, "r") as f:
        return json.load(f)

def guardar_posicoes(posicoes):
    with open(FICHEIRO_POSICOES, "w") as f:
        json.dump(posicoes, f, indent=2)

# ⚙️ Configuração geral
st.set_page_config(page_title="Painel RSI", layout="wide")
st.title("📈 Painel RSI com Indicadores Técnicos Avançados")

# Sidebar: filtros + navegação
st.sidebar.header("⚙️ Filtros")
tempo_refresco = st.sidebar.slider("⏳ Atualizar a cada (segundos)", 10, 300, 60, step=10)
timeframe = st.sidebar.selectbox("🕒 Intervalo de tempo", ["15m", "1h", "4h"], index=1)
exchanges_disponiveis = ['kucoin', 'coinbase', 'kraken']
exchange_nome = st.sidebar.selectbox("🌐 Exchange", exchanges_disponiveis, index=0)
filtro_alerta = st.sidebar.radio("⚠️ Tipo de alerta a mostrar", ["Todos", "ENTRADA", "SAÍDA", "NEUTRO"])

# 🔽 Menu de secções (AQUI ESTAVA A FALTAR!)
st.sidebar.markdown("---")
secao = st.sidebar.radio("📂 Secções", ["📊 Painel RSI", "💼 Minhas Posições"])

# 🔄 Atualização automática
st_autorefresh(interval=tempo_refresco * 1000, key="refresh")

# ============================
# 📊 PAINEL RSI
# ============================
if secao == "📊 Painel RSI":
    exchange = getattr(ccxt, exchange_nome)()
    estado_alertas = {}

    for moeda in MOEDAS:
        try:
            candles = exchange.fetch_ohlcv(moeda, timeframe=timeframe, limit=100)
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            df['RSI'] = RSIIndicator(close=df['close'], window=14).rsi()
            df['SMA'] = SMAIndicator(close=df['close'], window=14).sma_indicator()
            df['EMA'] = EMAIndicator(close=df['close'], window=14).ema_indicator()
            df['volume_medio'] = df['volume'].rolling(window=14).mean()

            macd = MACD(close=df['close'])
            df['MACD'] = macd.macd()
            df['MACD_signal'] = macd.macd_signal()

            bb = BollingerBands(close=df['close'], window=20, window_dev=2)
            df['BB_upper'] = bb.bollinger_hband()
            df['BB_lower'] = bb.bollinger_lband()

            rsi = df['RSI'].iloc[-1]
            preco = df['close'].iloc[-1]
            sma = df['SMA'].iloc[-1]
            ema = df['EMA'].iloc[-1]
            vol = df['volume'].iloc[-1]
            vol_med = df['volume_medio'].iloc[-1]
            macd_val = df['MACD'].iloc[-1]
            macd_sig = df['MACD_signal'].iloc[-1]
            bb_sup = df['BB_upper'].iloc[-1]
            bb_inf = df['BB_lower'].iloc[-1]

            st.subheader(f"📊 {moeda} ({exchange_nome})")
            col1, col2, col3 = st.columns(3)
            col1.metric("💰 Preço", f"{preco:.2f} USDT")
            col2.metric("📈 RSI", f"{rsi:.2f}")
            col3.metric("📊 SMA", f"{sma:.2f}")

            alerta = "NEUTRO"
            emoji = "ℹ️"
            if rsi < 30:
                alerta = "ENTRADA"
                emoji = "🔔"
            elif rsi > 70:
                alerta = "SAÍDA"
                emoji = "🔔"

            st.markdown(f"**{emoji} Estado: {alerta}**")

            confirmacao = []
            if alerta == "ENTRADA":
                if preco > sma: confirmacao.append("✅ preço > SMA")
                if preco > ema: confirmacao.append("✅ preço > EMA")
                if vol > vol_med: confirmacao.append("✅ volume alto")
                if macd_val > macd_sig: confirmacao.append("✅ MACD p/ cima")
                if preco < bb_inf: confirmacao.append("✅ fora da Bollinger inferior")
            elif alerta == "SAÍDA":
                if preco < sma: confirmacao.append("✅ preço < SMA")
                if preco < ema: confirmacao.append("✅ preço < EMA")
                if vol > vol_med: confirmacao.append("✅ volume alto")
                if macd_val < macd_sig: confirmacao.append("✅ MACD p/ baixo")
                if preco > bb_sup: confirmacao.append("✅ fora da Bollinger superior")
            else:
                confirmacao.append("ℹ️ RSI neutro")

            st.markdown("📋 **Análise**: " + " | ".join(confirmacao))

            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(df['close'], label='Preço', color='blue')
            ax.plot(df['SMA'], label='SMA', color='purple', linestyle='--')
            ax.plot(df['EMA'], label='EMA', color='green', linestyle='--')
            ax.plot(df['BB_upper'], label='BB Sup', color='grey', linestyle=':')
            ax.plot(df['BB_lower'], label='BB Inf', color='grey', linestyle=':')
            ax.set_title(f"{moeda} - Preço com SMA/EMA/Bollinger")
            ax.legend()
            st.pyplot(fig)

            buf = BytesIO()
            fig.savefig(buf, format="png")
            st.download_button(
                label="💾 Guardar gráfico como imagem",
                data=buf.getvalue(),
                file_name=f"{moeda.replace('/', '_')}_grafico.png",
                mime="image/png"
            )

            st.divider()

        except Exception as e:
            st.error(f"Erro ao carregar {moeda}: {e}")

# ============================
# 💼 REGISTO DE POSIÇÕES
# ============================
elif secao == "💼 Minhas Posições":
    st.title("💼 Registo de Posições Pessoais")

    with st.form("form_nova_posicao"):
        moeda = st.text_input("Moeda (ex: SOL/USDT)")
        montante = st.number_input("Montante investido (€)", min_value=0.0)
        preco = st.number_input("Preço de entrada (USDT)", min_value=0.0)
        submeter = st.form_submit_button("Guardar")

        if submeter and moeda and montante and preco:
            nova = {
                "moeda": moeda.upper(),
                "montante": montante,
                "preco_entrada": preco,
                "data": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            posicoes = carregar_posicoes()
            posicoes.append(nova)
            guardar_posicoes(posicoes)
            st.success("✅ Posição registada com sucesso!")

    st.subheader("📋 Posições Atuais")
    posicoes = carregar_posicoes()
    if posicoes:
        st.table(posicoes)
    else:
        st.info("Nenhuma posição registada.")
