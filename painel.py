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
import firebase_admin
from firebase_admin import credentials, firestore
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

# Lê a variável de ambiente como string
firebase_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
firebase_dict = json.loads(firebase_json)

# Inicializa o Firebase com o dicionário
cred = credentials.Certificate(firebase_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

firebase_admin.initialize_app(cred)
db = firestore.client()

# 📁 Base de dados local
FICHEIRO_POSICOES = "posicoes.json"
FICHEIRO_ESTRATEGIAS = "estrategia_log.csv"

def carregar_posicoes():
    docs = db.collection("posicoes").stream()
    return [doc.to_dict() for doc in docs]

def guardar_posicoes(posicoes):
    # Apagar todas as posições antigas
    for doc in db.collection("posicoes").stream():
        doc.reference.delete()
    # Adicionar as novas
    for pos in posicoes:
        db.collection("posicoes").add(pos)

def guardar_venda(registro):
    FICHEIRO_HISTORICO = "historico_vendas.json"
    historico = []
    if os.path.exists(FICHEIRO_HISTORICO):
        with open(FICHEIRO_HISTORICO, "r") as f:
            try:
                historico = json.load(f)
            except:
                historico = []
    historico.append(registro)
    with open(FICHEIRO_HISTORICO, "w") as f:
        json.dump(historico, f, indent=2)

# ⚙️ Configuração geral
st.set_page_config(page_title="Painel RSI", layout="wide")
st.title("📈 Painel RSI com Indicadores Técnicos Avançados")

# Sidebar: filtros + navegação
st.sidebar.header("⚙️ Filtros")
tempo_refresco = st.sidebar.slider("⏳ Atualizar a cada (segundos)", 10, 300, 60, step=10)
timeframe = st.sidebar.selectbox("🕒 Intervalo de tempo", ["15m", "1h", "4h"], index=1)
exchanges_disponiveis = ['kucoin', 'coinbase', 'kraken']
exchange_nome = st.sidebar.selectbox("🌐 Exchange", exchanges_disponiveis, index=0)

# 🔽 Menu de secções
st.sidebar.markdown("---")
secao = st.sidebar.radio("📂 Secções", ["📊 Painel RSI", "💼 Minhas Posições", "📈 Estratégias", "📜 Histórico de Vendas"])

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

    posicoes = carregar_posicoes()

    st.subheader("➕ Adicionar Nova Posição")

    moeda = st.text_input("Moeda (ex: SOL/USDT)").upper()
    montante = st.number_input("Montante investido (€)", min_value=0.0)
    preco = st.number_input("Preço de entrada (USDT)", min_value=0.0)
    objetivo = st.number_input("Objetivo de lucro (%)", min_value=0.0, value=10.0, step=0.5)

    exchange_validacao = ccxt.kucoin()  # Podes mudar conforme necessidade
    mercados = exchange_validacao.load_markets()
    confirmacao = False

    if moeda in mercados:
        st.success(f"🔍 Encontrado: {moeda} na exchange Kucoin.")
        confirmacao = True
    elif moeda:
        st.error(f"❌ Moeda '{moeda}' não encontrada na Kucoin.")

    with st.form("form_nova_posicao"):
        if confirmacao:
            submeter = st.form_submit_button("Guardar")
            if submeter and moeda and montante and preco:
                nova = {
                    "moeda": moeda,
                    "montante": montante,
                    "preco_entrada": preco,
                    "objetivo": objetivo,
                    "data": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                posicoes.append(nova)
                guardar_posicoes(posicoes)
                st.success("✅ Posição registada com sucesso!")
                st.rerun()

    st.markdown("---")
    st.subheader("📊 Posições Atuais com Lucro/Prejuízo")

    if posicoes:
        exchange = ccxt.kucoin()
        dados = []
        for i, pos in enumerate(posicoes):
            try:
                ticker = exchange.fetch_ticker(pos['moeda'])
                preco_atual = ticker['last']
                investido = pos['montante']
                preco_entrada = pos['preco_entrada']
                objetivo = pos.get('objetivo', 10.0)

                valor_atual = preco_atual * (investido / preco_entrada)
                lucro = valor_atual - investido
                percent = (lucro / investido) * 100
                atingiu_objetivo = percent >= objetivo

                dados.append({
                    "Index": i,
                    "Moeda": pos['moeda'],
                    "Data Entrada": pos['data'],
                    "Preço Entrada": preco_entrada,
                    "Preço Atual": round(preco_atual, 2),
                    "Investido (€)": round(investido, 2),
                    "Valor Atual (€)": round(valor_atual, 2),
                    "Lucro (€)": round(lucro, 2),
                    "Variação (%)": round(percent, 2),
                    "🎯 Objetivo (%)": objetivo,
                    "🏁 Alvo Atingido": "✅" if atingiu_objetivo else "❌"
                })
            except Exception as e:
                st.error(f"Erro ao buscar {pos['moeda']}: {e}")

        df = pd.DataFrame(dados)
        df = df.sort_values("Variação (%)", ascending=False)

        # Exibir tabela com estilo
        def cor_lucro(val):
            if isinstance(val, (float, int)):
                if val > 0:
                    return 'background-color: #d4edda'
                elif val < 0:
                    return 'background-color: #f8d7da'
            return ''

        def cor_alvo(val):
            return 'background-color: #d4edda' if val == '✅' else ''

        st.dataframe(
            df.drop(columns=["Index"]).style
              .applymap(cor_lucro, subset=['Lucro (€)', 'Variação (%)'])
              .applymap(cor_alvo, subset=['🏁 Alvo Atingido']),
            use_container_width=True
        )

        # 🛠️ Edição/Remoção
        st.markdown("### ✏️ Editar ou Remover Posição")
        index = st.number_input("Seleciona o índice da posição", min_value=0, max_value=len(posicoes)-1, step=1)
        pos = posicoes[index]

        with st.form("editar_posicao"):
            moeda = st.text_input("Moeda", value=pos["moeda"])
            montante = st.number_input("Montante investido (€)", value=pos["montante"])
            preco = st.number_input("Preço de entrada (USDT)", value=pos["preco_entrada"])
            objetivo = st.number_input("Objetivo de lucro (%)", value=pos.get("objetivo", 10.0))
            editar = st.form_submit_button("💾 Atualizar posição")

            if editar:
                posicoes[index] = {
                    "moeda": moeda.upper(),
                    "montante": montante,
                    "preco_entrada": preco,
                    "objetivo": objetivo,
                    "data": pos["data"]
                }
                guardar_posicoes(posicoes)
                st.success("✅ Posição atualizada!")
                st.rerun()

        if st.button("🗑️ Remover esta posição"):
            del posicoes[index]
            guardar_posicoes(posicoes)
            st.warning("❌ Posição removida.")
            st.rerun()

        # Exportar
        csv = df.drop(columns=["Index"]).to_csv(index=False).encode('utf-8')
        st.download_button("📥 Exportar posições", csv, "posicoes.csv", "text/csv")
    else:
        st.info("Ainda não registaste nenhuma posição.")

    with st.expander("➕ Reforçar esta posição"):
        novo_montante = st.number_input("Montante adicional (€)", min_value=0.0, key="reforco_montante")
        novo_preco = st.number_input("Preço da nova compra (USDT)", min_value=0.0, key="reforco_preco")
        if st.button("Aplicar Reforço"):
            if novo_montante > 0 and novo_preco > 0:
                antigo_montante = pos["montante"]
                antigo_preco = pos["preco_entrada"]
                total_valor = (antigo_montante / antigo_preco) + (novo_montante / novo_preco)
                novo_total_investido = antigo_montante + novo_montante
                novo_preco_medio = novo_total_investido / total_valor
                pos["montante"] = round(novo_total_investido, 2)
                pos["preco_entrada"] = round(novo_preco_medio, 4)
                guardar_posicoes(posicoes)
                st.success("✅ Reforço aplicado com sucesso!")
                st.rerun()

        if st.button("💰 Vendi esta posição"):
            try:
                ticker = ccxt.kucoin().fetch_ticker(pos["moeda"])
                preco_atual = ticker["last"]
                investido = pos["montante"]
                preco_entrada = pos["preco_entrada"]
                valor_final = preco_atual * (investido / preco_entrada)
                lucro = valor_final - investido
                percent = (lucro / investido) * 100

                registro = {
                    "moeda": pos["moeda"],
                    "data_venda": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "preco_venda": preco_atual,
                    "preco_entrada": preco_entrada,
                    "investido": investido,
                    "valor_final": round(valor_final, 2),
                    "lucro": round(lucro, 2),
                    "percentual": round(percent, 2)
                }
                guardar_venda(registro)
                del posicoes[index]
                guardar_posicoes(posicoes)
                st.success("✅ Posição vendida e registada no histórico.")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao vender posição: {e}")

# ============================
# 📈 ESTRATÉGIAS
# ============================
elif secao == "📈 Estratégias":
    st.title("📈 Estratégias Automáticas Detetadas")
    if os.path.exists(FICHEIRO_ESTRATEGIAS):
        try:
            df = pd.read_csv(FICHEIRO_ESTRATEGIAS)
            if not df.empty:
                st.dataframe(df, use_container_width=True)
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button("📥 Exportar CSV", csv, "estrategias.csv", "text/csv")
            else:
                st.info("Nenhuma estratégia registada ainda.")
        except Exception as e:
            st.error(f"❌ Erro ao carregar estratégias: {e}")
    else:
        st.warning("Ficheiro de estratégias não encontrado.")

# ============================
# 📜 HISTÓRICO DE VENDAS
# ============================
elif secao == "📜 Histórico de Vendas":
    FICHEIRO_HISTORICO = "historico_vendas.json"
    st.title("📜 Histórico de Vendas Realizadas")
    if os.path.exists(FICHEIRO_HISTORICO):
        with open(FICHEIRO_HISTORICO, "r") as f:
            vendas = json.load(f)
        if vendas:
            df = pd.DataFrame(vendas)
            st.dataframe(df, use_container_width=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Exportar CSV", csv, "historico_vendas.csv", "text/csv")
        else:
            st.info("Nenhuma venda registada ainda.")
    else:
        st.warning("Ficheiro de histórico não encontrado.")

