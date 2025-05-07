import streamlit as st
import pandas as pd
import time
import matplotlib.pyplot as plt
import ccxt
from ta.momentum import RSIIndicator
from config import MOEDAS, LOG_PATH
from io import BytesIO

# ⚙️ Configuração inicial
st.set_page_config(page_title="Monitor RSI Cripto", layout="wide")
st.title("📈 Painel RSI de Criptomoedas")

# ======================
# 🔧 SIDEBAR (filtros)
# ======================
st.sidebar.header("⚙️ Filtros")

tempo_refresco = st.sidebar.slider("⏳ Atualizar a cada (segundos)", 10, 300, 60, step=10)
timeframe = st.sidebar.selectbox("🕒 Intervalo de tempo", options=["15m", "1h", "4h"], index=1)
exchanges_disponiveis = ['kucoin', 'coinbase', 'kraken']
exchange_nome = st.sidebar.selectbox("🌐 Exchange", exchanges_disponiveis, index=0)
filtro_alerta = st.sidebar.radio("⚠️ Tipo de alerta a mostrar", options=["Todos", "ENTRADA", "SAÍDA", "NEUTRO"])

# ======================
# 🔌 Conectar à exchange
# ======================
try:
    exchange_class = getattr(ccxt, exchange_nome)
    exchange = exchange_class()
except AttributeError:
    st.error(f"Exchange '{exchange_nome}' não é suportada pelo ccxt.")
    st.stop()

# ======================
# ♻️ LOOP de atualização
# ======================
while True:
    for moeda in MOEDAS:
        try:
            candles = exchange.fetch_ohlcv(moeda, timeframe=timeframe, limit=100)
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            rsi = RSIIndicator(close=df['close'], window=14)
            df['RSI'] = rsi.rsi()

            rsi_atual = df['RSI'].iloc[-1]
            preco_atual = df['close'].iloc[-1]

            st.subheader(f"📊 {moeda} ({exchange_nome})")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("💰 Preço", f"{preco_atual:.2f} USDT")
            with col2:
                st.metric("📈 RSI", f"{rsi_atual:.2f}")
            with col3:
                if rsi_atual < 30:
                    st.success("🔔 ENTRADA")
                elif rsi_atual > 70:
                    st.warning("🔔 SAÍDA")
                else:
                    st.info("ℹ️ NEUTRO")

            # === Gráfico RSI + Preço ===
            st.markdown("#### Gráfico RSI e Preço")
            fig, ax1 = plt.subplots(figsize=(8, 3))
            ax2 = ax1.twinx()
            ax1.plot(df['RSI'], color='orange', label='RSI')
            ax2.plot(df['close'], color='blue', label='Preço')
            ax1.set_ylabel('RSI', color='orange')
            ax2.set_ylabel('Preço', color='blue')
            ax1.axhline(30, color='green', linestyle='--', linewidth=1)
            ax1.axhline(70, color='red', linestyle='--', linewidth=1)
            ax1.set_title(f"{moeda} - RSI & Preço")
            st.pyplot(fig)

            # ✅ Botão para guardar gráfico
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

    # ======================
    # 📜 Histórico de Alertas
    # ======================
    st.markdown("### 📜 Histórico de Alertas")
    try:
        df_log = pd.read_csv(LOG_PATH)
        if filtro_alerta != "Todos":
            df_log = df_log[df_log['Alerta'] == filtro_alerta]

        st.dataframe(df_log.tail(20), use_container_width=True)

        # ✅ Botão para exportar histórico
        csv = df_log.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📤 Exportar histórico filtrado para CSV",
            data=csv,
            file_name="alertas_filtrados.csv",
            mime="text/csv"
        )

    except Exception as e:
        st.warning("Histórico não disponível.")

    time.sleep(tempo_refresco)
    st.experimental_rerun()
