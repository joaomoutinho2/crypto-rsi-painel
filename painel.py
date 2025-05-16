"""
📊 Painel RSI com Indicadores Técnicos Avançados

Este painel permite acompanhar sinais de entrada/saída baseados em RSI, EMA, MACD, Bollinger Bands,
gerir posições ativas, vendas realizadas e visualizar estratégias automáticas. Assegura comunicação
com Firestore e envio de alertas por Telegram.
"""

# ============================
# 📦 IMPORTAÇÕES E CONFIGURAÇÃO
# ============================

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import ccxt
import os
import json
import sys
from datetime import datetime
from io import BytesIO
import base64

from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.volatility import BollingerBands
from streamlit_autorefresh import st_autorefresh

from config import MOEDAS, LOG_PATH
from firebase_config import iniciar_firebase
from firebase_admin import firestore
from telegram_alert import enviar_telegram

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ✅ Inicializar Firestore com secrets
st.set_page_config(page_title="Painel RSI", layout="wide")
db = iniciar_firebase(usando_secrets=True, secrets=st.secrets)

# ============================
# 🔁 FUNÇÕES FIRESTORE
# ============================

def carregar_posicoes():
    try:
        docs = db.collection("posicoes").stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        st.error(f"❌ Erro ao carregar posições: {e}")
        return []

def guardar_posicoes(posicoes):
    try:
        for doc in db.collection("posicoes").stream():
            doc.reference.delete()
        for pos in posicoes:
            db.collection("posicoes").add(pos)
    except Exception as e:
        st.error(f"❌ Erro ao guardar posições: {e}")

def guardar_venda(registro):
    try:
        db.collection("historico_vendas").add(registro)
    except Exception as e:
        st.error(f"❌ Erro ao guardar venda: {e}")

def carregar_historico_vendas():
    try:
        docs = db.collection("historico_vendas").stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        st.error(f"❌ Erro ao carregar histórico de vendas: {e}")
        return []

def carregar_modelo_treinado():
    try:
        docs = db.collection("modelos_treinados").order_by("data_treino", direction=firestore.Query.DESCENDING).limit(1).stream()
        for doc in docs:
            dados = doc.to_dict()
            modelo_b64 = dados.get("modelo")
            if modelo_b64:
                buffer = BytesIO(base64.b64decode(modelo_b64))
                return joblib.load(buffer)
        st.warning("⚠️ Nenhum modelo encontrado.")
    except Exception as e:
        st.error(f"❌ Erro ao carregar modelo: {e}")
    return None

# ============================
# 🎛️ SIDEBAR E OPÇÕES DE CONTROLO
# ============================

st.title("📈 Painel RSI com Indicadores Técnicos")

st.sidebar.header("⚙️ Filtros e Opções")
tempo_refresco = st.sidebar.slider("⏳ Atualizar a cada (segundos)", 10, 300, 60, step=10)
timeframe = st.sidebar.selectbox("🕒 Intervalo de tempo", ["15m", "1h", "4h"], index=1)
exchange_nome = st.sidebar.selectbox("🌐 Exchange", ["kucoin", "coinbase", "kraken"], index=0)
secao = st.sidebar.radio("📂 Secções", ["📊 Painel RSI", "💼 Minhas Posições", "📜 Histórico de Vendas", "⚙️ Estratégias"])

# Refresh automático
st_autorefresh(interval=tempo_refresco * 1000, key="refresh")
# ... (mantém-se o código já refatorado anteriormente)

# ============================
# 📊 ÚLTIMO MODELO TREINADO
# ============================
if secao == "📊 Último Modelo Treinado":
    st.title("📊 Último Modelo Treinado com Dados Reais")
    doc = carregar_modelo_treinado()
    if doc:
        modelo = doc.to_dict()
        st.markdown(f"**🧠 Modelo:** [dados ocultos base64]") 
        st.markdown(f"**📅 Data de treino:** {modelo.get('data_treino', 'N/A')}")
        st.markdown(f"**🎯 Acurácia:** {modelo.get('acuracia', 0):.2%}")

        st.markdown("---")
        st.subheader("📊 Relatório de Classificação")
        relatorio = modelo.get("relatorio", {})
        if relatorio:
            st.dataframe(pd.DataFrame(relatorio).T)

        st.subheader("🧱 Matriz de Confusão")
        matriz = pd.DataFrame(
            modelo.get("matriz_confusao", []),
            columns=["Previsto Negativo", "Previsto Positivo"],
            index=["Real Negativo", "Real Positivo"]
        )
        st.dataframe(matriz)
    else:
        st.warning("⚠️ Nenhum modelo treinado disponível.")

# ============================
# 📊 PAINEL RSI AO VIVO
# ============================
if secao == "📊 Painel RSI":
    st.title("📊 Painel RSI ao Vivo")
    exchange = getattr(ccxt, exchange_nome)()

    for moeda in MOEDAS:
        try:
            candles = exchange.fetch_ohlcv(moeda, timeframe=timeframe, limit=100)
            df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])

            # 📈 Indicadores Técnicos
            df["RSI"] = RSIIndicator(df["close"]).rsi()
            df["SMA"] = SMAIndicator(df["close"]).sma_indicator()
            df["EMA"] = EMAIndicator(df["close"]).ema_indicator()
            df["volume_medio"] = df["volume"].rolling(window=14).mean()

            macd = MACD(df["close"])
            df["MACD"] = macd.macd()
            df["MACD_signal"] = macd.macd_signal()

            bb = BollingerBands(df["close"])
            df["BB_upper"] = bb.bollinger_hband()
            df["BB_lower"] = bb.bollinger_lband()

            # Últimos valores
            rsi = df["RSI"].iloc[-1]
            preco = df["close"].iloc[-1]
            sma = df["SMA"].iloc[-1]
            ema = df["EMA"].iloc[-1]
            vol = df["volume"].iloc[-1]
            vol_med = df["volume_medio"].iloc[-1]
            macd_val = df["MACD"].iloc[-1]
            macd_sig = df["MACD_signal"].iloc[-1]
            bb_sup = df["BB_upper"].iloc[-1]
            bb_inf = df["BB_lower"].iloc[-1]

            st.subheader(f"📊 {moeda} ({exchange_nome})")
            col1, col2, col3 = st.columns(3)
            col1.metric("💰 Preço", f"{preco:.2f} USDT")
            col2.metric("📈 RSI", f"{rsi:.2f}")
            col3.metric("📊 SMA", f"{sma:.2f}")

            col4, col5, col6 = st.columns(3)
            col4.metric("📉 MACD", f"{macd_val:.2f}")
            col5.metric("🎯 MACD Signal", f"{macd_sig:.2f}")
            col6.metric("📊 Volume Atual", f"{vol:.0f}")

            col7, col8 = st.columns(2)
            col7.metric("📈 EMA", f"{ema:.2f}")
            col8.metric("📦 Vol. Médio", f"{vol_med:.0f}")

            st.caption(f"📉 Bollinger Bands: Inferior = {bb_inf:.2f}, Superior = {bb_sup:.2f}")

            alerta = "ℹ️ Neutro"
            if rsi < 30:
                alerta = "🟢 Sinal de entrada (RSI < 30)"
            elif rsi > 70:
                alerta = "🔴 Sinal de saída (RSI > 70)"
            st.success(alerta if "Sinal" in alerta else alerta)

        except Exception as e:
            st.error(f"❌ Erro ao processar {moeda}: {e}")
# ... (continuação do painel anterior)

            # 🔎 Confirmações adicionais
            confirmacao = []
            if alerta == "🟢 Sinal de entrada (RSI < 30)":
                if preco > sma: confirmacao.append("✅ preço > SMA")
                if preco > ema: confirmacao.append("✅ preço > EMA")
                if vol > vol_med: confirmacao.append("✅ volume alto")
                if macd_val > macd_sig: confirmacao.append("✅ MACD p/ cima")
                if preco < bb_inf: confirmacao.append("✅ fora da Bollinger inferior")
            elif alerta == "🔴 Sinal de saída (RSI > 70)":
                if preco < sma: confirmacao.append("✅ preço < SMA")
                if preco < ema: confirmacao.append("✅ preço < EMA")
                if vol > vol_med: confirmacao.append("✅ volume alto")
                if macd_val < macd_sig: confirmacao.append("✅ MACD p/ baixo")
                if preco > bb_sup: confirmacao.append("✅ fora da Bollinger superior")
            else:
                confirmacao.append("ℹ️ RSI neutro")

            st.markdown("📋 **Análise Técnica**: " + " | ".join(confirmacao))

            # 📉 Gráfico de preço com indicadores
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(df['close'], label='Preço', color='blue')
            ax.plot(df['SMA'], label='SMA', color='purple', linestyle='--')
            ax.plot(df['EMA'], label='EMA', color='green', linestyle='--')
            ax.plot(df['BB_upper'], label='BB Sup', color='grey', linestyle=':')
            ax.plot(df['BB_lower'], label='BB Inf', color='grey', linestyle=':')
            ax.set_title(f"{moeda} - Indicadores Técnicos")
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
            st.error(f"❌ Erro ao carregar {moeda}: {e}")

# ============================
# 💼 REGISTO DE POSIÇÕES
# ============================
elif secao == "💼 Minhas Posições":
    st.title("💼 Registo de Posições Pessoais")
    posicoes = carregar_posicoes()

    st.subheader("➕ Adicionar Nova Posição")
    moeda = st.text_input("Moeda (ex: SOL/USDT)").upper()
    montante = st.number_input("Montante investido (€)", min_value=0.0)
    preco = st.number_input("Preço de entrada (USDT)", min_value=0.0)
    objetivo = st.number_input("Objetivo de lucro (%)", min_value=0.0, value=10.0, step=0.5)

    with st.form("form_nova_posicao"):
        submeter = st.form_submit_button("Guardar")
        if submeter and moeda and montante > 0 and preco > 0:
            nova = {
                "simbolo": moeda,
                "montante": montante,
                "preco_entrada": preco,
                "objetivo": objetivo,
                "data": datetime.utcnow()
            }
            db.collection("posicoes").add(nova)
            st.success("✅ Posição guardada com sucesso!")
            st.experimental_rerun()

    st.subheader("📋 Posições Atuais")
    if posicoes:
        df_pos = pd.DataFrame(posicoes)
        st.dataframe(df_pos)
    else:
        st.info("Nenhuma posição registada.")
# ... (continuação anterior)

# ============================
# 📜 HISTÓRICO DE VENDAS
# ============================
elif secao == "📜 Histórico de Vendas":
    st.title("📜 Histórico de Vendas Realizadas")
    try:
        vendas = carregar_historico_vendas()
        if vendas:
            df = pd.DataFrame(vendas)
            st.dataframe(df, use_container_width=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Exportar CSV", csv, "historico_vendas.csv", "text/csv")
        else:
            st.info("ℹ️ Nenhuma venda registada ainda.")
    except Exception as e:
        st.error(f"❌ Erro ao carregar histórico de vendas: {e}")

# ============================
# 📈 ESTRATÉGIAS DETETADAS
# ============================
elif secao == "📈 Estratégias":
    st.title("📈 Estratégias Automáticas Detetadas")
    try:
        docs = db.collection("estrategias").order_by("Data", direction=firestore.Query.DESCENDING).limit(100).stream()
        estrategias = [doc.to_dict() for doc in docs]
        if estrategias:
            df = pd.DataFrame(estrategias)
            st.dataframe(df, use_container_width=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Exportar CSV", csv, "estrategias.csv", "text/csv")
        else:
            st.info("ℹ️ Nenhuma estratégia registada ainda.")
    except Exception as e:
        st.error(f"❌ Erro ao carregar estratégias: {e}")

# ============================
# 📊 DESEMPENHO DO BOT
# ============================
elif secao == "📊 Desempenho do Bot":
    st.title("📊 Estado e Desempenho do Bot")

    # 🔎 Progresso do campo 'preco_entrada'
    st.subheader("🛠️ Atualização de 'preco_entrada'")
    try:
        docs = db.collection("historico_previsoes").stream()
        total, com_preco = 0, 0
        for doc in docs:
            data = doc.to_dict()
            total += 1
            if "preco_entrada" in data:
                com_preco += 1
        sem_preco = total - com_preco

        if total > 0:
            st.write(f"✅ {com_preco} com preço • ❌ {sem_preco} sem preço • Total: {total}")
            st.progress(com_preco / total)

            fig, ax = plt.subplots()
            ax.pie([com_preco, sem_preco], labels=["Com preço", "Sem preço"], autopct='%1.1f%%', colors=["#4CAF50", "#F44336"])
            ax.axis("equal")
            st.pyplot(fig)
        else:
            st.info("ℹ️ Nenhum documento encontrado em 'historico_previsoes'.")
    except Exception as e:
        st.error(f"❌ Erro ao verificar progresso de 'preco_entrada': {e}")

    # 🎯 Acertos do modelo
    st.subheader("🎯 Taxa de Acerto do Bot")
    try:
        docs = db.collection("historico_previsoes").stream()
        dados = [doc.to_dict() for doc in docs if "Previsao" in doc.to_dict() and "resultado" in doc.to_dict()]
        df = pd.DataFrame(dados)
        df = df[df["resultado"].isin([0, 1])]
        df["acertou"] = df["Previsao"] == df["resultado"]

        acertos = df["acertou"].value_counts().rename(index={True: "Acertos", False: "Erros"})
        st.bar_chart(acertos)

        st.subheader("📈 Acertos por Moeda")
        acertos_moeda = df.groupby("Moeda")["acertou"].mean().sort_values(ascending=False)
        st.dataframe(acertos_moeda.map(lambda x: f"{x:.2%}"), use_container_width=True)

        st.subheader("📅 Previsões ao Longo do Tempo")
        df["Data"] = pd.to_datetime(df["Data"])
        historico = df.groupby(df["Data"].dt.date)["acertou"].mean()
        st.line_chart(historico)

    except Exception as e:
        st.error(f"❌ Erro ao carregar desempenho: {e}")

    # 💰 Lucro por moeda
    st.subheader("💰 Lucro Acumulado por Moeda")
    try:
        vendas = db.collection("historico_vendas").stream()
        vendas_dados = [doc.to_dict() for doc in vendas if "moeda" in doc.to_dict() and "lucro" in doc.to_dict()]
        if vendas_dados:
            df_vendas = pd.DataFrame(vendas_dados)
            df_vendas["lucro"] = pd.to_numeric(df_vendas["lucro"], errors="coerce")
            lucro_moeda = df_vendas.groupby("moeda")["lucro"].sum().sort_values(ascending=False)
            st.bar_chart(lucro_moeda)
            st.dataframe(lucro_moeda.rename("Lucro Total (USDT)").map(lambda x: f"{x:.2f}"), use_container_width=True)
        else:
            st.info("ℹ️ Ainda não há vendas registadas.")
    except Exception as e:
        st.error(f"❌ Erro ao carregar histórico de vendas: {e}")