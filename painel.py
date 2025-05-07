import streamlit as st
import pandas as pd
import time
import matplotlib.pyplot as plt
from utils import fetch_ohlcv, calcular_rsi
from config import MOEDAS, LOG_PATH

# ⚙️ Configuração da página
st.set_page_config(page_title="Monitor RSI Cripto", layout="wide")
st.title("📈 Painel RSI de Criptomoedas")

# ⏱️ Parâmetros do utilizador
col_filtros = st.sidebar
col_filtros.header("🔧 Filtros")

tempo_refresco = col_filtros.slider("⏳ Atualizar a cada (segundos)", 10, 300, 60, step=10)
timeframe = col_filtros.selectbox("🕒 Intervalo de tempo", options=["15m", "1h", "4h"], index=1)
filtro_alerta = col_filtros.radio("⚠️ Tipo de alerta a mostrar no histórico", options=["Todos", "ENTRADA", "SAÍDA", "NEUTRO"])

st.caption(f"Painel atualizado automaticamente a cada {tempo_refresco} segundos com intervalo '{timeframe}'")

# ♻️ Loop de atualização
while True:
    for moeda in MOEDAS:
        try:
            df = fetch_ohlcv(moeda, timeframe=timeframe)
            df = calcular_rsi(df)
            rsi_atual = df['RSI'].iloc[-1]
            preco_atual = df['close'].iloc[-1]

            st.subheader(f"📊 {moeda}")
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

            # Gráfico RSI e Preço
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

            st.divider()

        except Exception as e:
            st.error(f"Erro ao carregar {moeda}: {e}")

    # Histórico filtrado
    st.markdown("### 📜 Histórico de Alertas")
    try:
        df_log = pd.read_csv(LOG_PATH)
        if filtro_alerta != "Todos":
            df_log = df_log[df_log['Alerta'] == filtro_alerta]
        st.dataframe(df_log.tail(20), use_container_width=True)
    except Exception as e:
        st.warning("Histórico não disponível ou ficheiro não existe.")

    time.sleep(tempo_refresco)
    st.experimental_rerun()
