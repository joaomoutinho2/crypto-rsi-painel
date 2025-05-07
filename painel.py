import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import ccxt
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
from config import MOEDAS, LOG_PATH
from io import BytesIO
from streamlit_autorefresh import st_autorefresh
from telegram_alert import enviar_telegram

# ⚙️ Configuração inicial
st.set_page_config(page_title="Painel RSI com Análise", layout="wide")
st.title("📈 Painel RSI Inteligente com Confirmações")

# 🔧 SIDEBAR (Filtros)
st.sidebar.header("⚙️ Filtros")
tempo_refresco = st.sidebar.slider("⏳ Atualizar a cada (segundos)", 10, 300, 60, step=10)
timeframe = st.sidebar.selectbox("🕒 Intervalo de tempo", ["15m", "1h", "4h"], index=1)
exchanges_disponiveis = ['kucoin', 'coinbase', 'kraken']
exchange_nome = st.sidebar.selectbox("🌐 Exchange", exchanges_disponiveis, index=0)
filtro_alerta = st.sidebar.radio("⚠️ Tipo de alerta a mostrar", ["Todos", "ENTRADA", "SAÍDA", "NEUTRO"])

# 🔁 Autoatualização
st_autorefresh(interval=tempo_refresco * 1000, key="refresh")

# 🔌 Ligação à exchange
exchange = getattr(ccxt, exchange_nome)()
estado_alertas = {}

# 📊 Análise por moeda
for moeda in MOEDAS:
    try:
        candles = exchange.fetch_ohlcv(moeda, timeframe=timeframe, limit=100)
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        df['RSI'] = RSIIndicator(close=df['close'], window=14).rsi()
        df['SMA'] = SMAIndicator(close=df['close'], window=14).sma_indicator()
        df['volume_medio'] = df['volume'].rolling(window=14).mean()

        rsi_atual = df['RSI'].iloc[-1]
        preco_atual = df['close'].iloc[-1]
        sma_atual = df['SMA'].iloc[-1]
        vol_atual = df['volume'].iloc[-1]
        vol_medio = df['volume_medio'].iloc[-1]

        st.subheader(f"📊 {moeda} ({exchange_nome})")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("💰 Preço", f"{preco_atual:.2f} USDT")
        with col2:
            st.metric("📈 RSI", f"{rsi_atual:.2f}")
        with col3:
            st.metric("📊 SMA (14)", f"{sma_atual:.2f}")

        # Determinar alerta e confirmação
        if rsi_atual < 30:
            alerta = "ENTRADA"
            emoji = "🔔"
        elif rsi_atual > 70:
            alerta = "SAÍDA"
            emoji = "🔔"
        else:
            alerta = "NEUTRO"
            emoji = "ℹ️"

        st.markdown(f"**{emoji} Estado: {alerta}**")

        # Análise adicional
        if alerta == "ENTRADA" and preco_atual > sma_atual and vol_atual > vol_medio:
            confirmacao = "✅ RSI em sobrevenda + preço acima da média + volume alto"
        elif alerta == "SAÍDA" and preco_atual < sma_atual and vol_atual > vol_medio:
            confirmacao = "✅ RSI em sobrecompra + preço abaixo da média + volume alto"
        elif alerta == "NEUTRO":
            confirmacao = "ℹ️ RSI em zona neutra"
        else:
            confirmacao = "⚠️ Sem confirmação forte"

        st.markdown(f"**📋 Análise:** {confirmacao}")

        # Enviar alerta Telegram se mudar
        alerta_anterior = estado_alertas.get(moeda)
        if alerta != alerta_anterior:
            mensagem = (
                f"📈 Alerta RSI - {moeda} ({exchange_nome})\n"
                f"⏱️ Timeframe: {timeframe}\n"
                f"💰 Preço: {preco_atual:.2f} USDT\n"
                f"📊 RSI: {rsi_atual:.2f} | SMA: {sma_atual:.2f}\n"
                f"📉 Volume: {vol_atual:.2f} (média: {vol_medio:.2f})\n"
                f"{emoji} Sinal: {alerta}\n"
                f"{confirmacao}"
            )
            enviar_telegram(mensagem)
            estado_alertas[moeda] = alerta

        # Gráfico
        st.markdown("#### RSI, Preço e SMA")
        fig, ax1 = plt.subplots(figsize=(8, 3))
        ax2 = ax1.twinx()
        ax1.plot(df['RSI'], color='orange', label='RSI')
        ax2.plot(df['close'], color='blue', label='Preço')
        ax2.plot(df['SMA'], color='purple', linestyle='--', label='SMA')
        ax1.axhline(30, color='green', linestyle='--', linewidth=1)
        ax1.axhline(70, color='red', linestyle='--', linewidth=1)
        ax1.set_ylabel('RSI', color='orange')
        ax2.set_ylabel('Preço', color='blue')
        st.pyplot(fig)

        # Botão para guardar imagem
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

# 📜 Histórico de Alertas
st.markdown("### 📜 Histórico de Alertas")
try:
    df_log = pd.read_csv(LOG_PATH)
    if filtro_alerta != "Todos":
        df_log = df_log[df_log['Alerta'] == filtro_alerta]

    st.dataframe(df_log.tail(20), use_container_width=True)

    csv = df_log.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📤 Exportar histórico filtrado para CSV",
        data=csv,
        file_name="alertas_filtrados.csv",
        mime="text/csv"
    )
except:
    st.warning("Histórico não disponível.")
