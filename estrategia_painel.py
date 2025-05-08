import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="📋 Estratégias Detetadas", layout="wide")
st.title("📋 Histórico de Estratégias Automáticas")

FICHEIRO = "estrategia_log.csv"

# 📥 Carregar ficheiro
if os.path.exists(FICHEIRO):
    df = pd.read_csv(FICHEIRO)

    # Filtros na sidebar
    st.sidebar.header("🔎 Filtros")
    moedas = sorted(df['Moeda'].unique())
    moeda_filtro = st.sidebar.multiselect("Filtrar por moeda", moedas, default=moedas)
    direcao_filtro = st.sidebar.radio("Tipo de sinal", ["Todos", "ENTRADA", "SAÍDA"])

    df_filtrado = df[df['Moeda'].isin(moeda_filtro)]
    if direcao_filtro != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Direcao"] == direcao_filtro]

    # Ordenar
    st.sidebar.markdown("📊 Ordenar por:")
    ordem = st.sidebar.selectbox("Coluna", ["Data", "Moeda", "Preço", "Sinais", "RSI", "Variação (%)"], index=0)
    asc = st.sidebar.checkbox("⬆️ Ordem crescente", value=False)

    if ordem in df_filtrado.columns:
        df_filtrado = df_filtrado.sort_values(ordem, ascending=asc)

    # Tabela principal
    st.dataframe(df_filtrado, use_container_width=True)

    # 📤 Exportar CSV
    csv = df_filtrado.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Exportar CSV", csv, "estrategia_filtrada.csv", "text/csv")
else:
    st.warning("Nenhuma estratégia registada ainda.")
