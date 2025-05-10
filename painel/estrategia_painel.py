import streamlit as st
import pandas as pd
from utils.firebase_config import iniciar_firebase

st.set_page_config(page_title="📋 Estratégias Detetadas", layout="wide")
st.title("📋 Histórico de Estratégias Automáticas")

# 🔥 Inicializar Firestore
db = iniciar_firebase(usando_secrets=True, secrets=st.secrets)

try:
    # 📥 Carregar dados da Firestore
    docs = db.collection("estrategias").stream()
    df = pd.DataFrame([doc.to_dict() for doc in docs])

    if not df.empty:
        # ================================
        # 🔎 Filtros na Sidebar
        # ================================
        st.sidebar.header("🔎 Filtros")

        moedas = sorted(df['Moeda'].unique())
        moeda_filtro = st.sidebar.multiselect("Filtrar por moeda", moedas, default=moedas)

        direcao_filtro = st.sidebar.radio("Tipo de sinal", ["Todos", "ENTRADA", "SAÍDA"])

        df_filtrado = df[df['Moeda'].isin(moeda_filtro)]
        if direcao_filtro != "Todos":
            df_filtrado = df_filtrado[df_filtrado["Direcao"] == direcao_filtro]

        # ================================
        # 📊 Ordenar
        # ================================
        st.sidebar.markdown("📊 Ordenar por:")
        ordem = st.sidebar.selectbox("Coluna", ["Data", "Moeda", "Preço", "Sinais", "RSI", "Variação (%)"], index=0)
        asc = st.sidebar.checkbox("⬆️ Ordem crescente", value=False)

        if ordem in df_filtrado.columns:
            df_filtrado = df_filtrado.sort_values(ordem, ascending=asc)

        # ================================
        # 📈 Tabela principal
        # ================================
        st.dataframe(df_filtrado, use_container_width=True)

        # 📤 Exportar CSV
        csv = df_filtrado.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Exportar CSV", csv, "estrategia_filtrada.csv", "text/csv")

    else:
        st.info("Nenhuma estratégia registada ainda.")

except Exception as e:
    st.error(f"❌ Erro ao carregar estratégias da Firestore: {e}")
