import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import ccxt
import os
import json
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime
from io import BytesIO

from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.volatility import BollingerBands

from streamlit_autorefresh import st_autorefresh

from config import MOEDAS, LOG_PATH
from firebase_config import iniciar_firebase
from firebase_admin import firestore
from telegram_alert import enviar_telegram

# ✅ Inicializar Firestore com secrets do Streamlit
db = iniciar_firebase(usando_secrets=True, secrets=st.secrets)

# ============================
# 🔁 Funções Firestore
# ============================

def carregar_posicoes():
    try:
        docs = db.collection("posicoes").stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        st.error(f"❌ Erro ao carregar posições do Firestore: {e}")
        return []

def guardar_posicoes(posicoes):
    try:
        for doc in db.collection("posicoes").stream():
            doc.reference.delete()
        for pos in posicoes:
            db.collection("posicoes").add(pos)
    except Exception as e:
        st.error(f"❌ Erro ao guardar posições no Firestore: {e}")

def guardar_venda(registro):
    try:
        db.collection("historico_vendas").add(registro)
    except Exception as e:
        st.error(f"❌ Erro ao guardar histórico de vendas: {e}")

def carregar_historico_vendas():
    try:
        docs = db.collection("historico_vendas").stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        st.error(f"❌ Erro ao carregar histórico de vendas: {e}")
        return []

def carregar_modelo_treinado():
    try:
        docs = db.collection("modelos_treinados").order_by("data_treino", direction=firestore.Query.DESCENDING).limit(5).stream()
        for doc in docs:
            dados = doc.to_dict()
            if "resultado" not in dados:
                st.warning(f"⚠️ Documento ignorado: {doc.id} - Faltam campos: ['resultado']")
                continue
            return doc
        return None
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados do modelo treinado: {e}")
        return None

# ============================
# ⚙️ Configuração Geral
# ============================

st.set_page_config(page_title="Painel RSI", layout="wide")
st.title("📈 Painel RSI com Indicadores Técnicos Avançados")

st.sidebar.header("⚙️ Filtros")
tempo_refresco = st.sidebar.slider("⏳ Atualizar a cada (segundos)", 10, 300, 60, step=10)
timeframe = st.sidebar.selectbox("🕒 Intervalo de tempo", ["15m", "1h", "4h"], index=1)
exchanges_disponiveis = ['kucoin', 'coinbase', 'kraken']
exchange_nome = st.sidebar.selectbox("🌐 Exchange", exchanges_disponiveis, index=0)

st.sidebar.markdown("---")
secao = st.sidebar.radio("📂 Secções", [
    "📊 Painel RSI",
    "💼 Minhas Posições",
    "📈 Estratégias",
    "📜 Histórico de Vendas",
    "📊 Último Modelo Treinado",
    "📊 Desempenho do Bot",
    "💸 Simulação de Capital Virtual"
])

st_autorefresh(interval=tempo_refresco * 1000, key="refresh")

# ============================
# 📊 ÚLTIMO MODELO TREINADO
# ============================
if secao == "📊 Último Modelo Treinado":
    st.title("📊 Último Modelo Treinado com Dados Reais")
    doc = carregar_modelo_treinado()
    if doc:
        modelo = doc.to_dict()
        st.markdown(f"**🧠 Modelo:** {modelo['modelo']}") 
        st.markdown(f"**📅 Data de treino:** {modelo['data_treino']}")
        st.markdown(f"**🎯 Acurácia:** {modelo['acuracia']:.2%}")

        st.markdown("---")
        st.subheader("📊 Relatório de Classificação")
        relatorio = modelo.get("relatorio", {})
        st.dataframe(pd.DataFrame(relatorio).T)

        st.subheader("🧱 Matriz de Confusão")
        matriz = pd.DataFrame(
            modelo.get("matriz_confusao", []),
            columns=["Previsto Negativo", "Previsto Positivo"],
            index=["Real Negativo", "Real Positivo"]
        )
        st.dataframe(matriz)
    else:
        st.warning("Nenhum modelo treinado disponível no momento.")

# ============================
# 📊 PAINEL RSI
# ============================
if secao == "📊 Painel RSI":
    st.title("📊 Painel RSI")
    exchange = getattr(ccxt, exchange_nome)()

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

            # Últimos valores
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

            # Gráfico
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(df['close'], label='Preço', color='blue')
            ax.plot(df['SMA'], label='SMA', color='purple', linestyle='--')
            ax.plot(df['EMA'], label='EMA', color='green', linestyle='--')
            ax.plot(df['BB_upper'], label='BB Sup', color='grey', linestyle=':')
            ax.plot(df['BB_lower'], label='BB Inf', color='grey', linestyle=':')
            ax.set_title(f"{moeda} - Preço com SMA/EMA/Bollinger")
            ax.legend()
            st.pyplot(fig)

            # Download do gráfico
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

    with st.form("form_nova_posicao"):
        submeter = st.form_submit_button("Guardar")
        if submeter and moeda and montante > 0 and preco > 0:
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

        # Exibir tabela com estilo condicional
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

        # Edição ou remoção
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

        # ✅ Reforçar posição com atualização Firestore
        st.markdown("### ➕ Reforçar Posição")
        novo_montante = st.number_input("Montante adicional (€)", min_value=0.0, key="reforco_montante")
        novo_preco = st.number_input("Preço da nova compra (USDT)", min_value=0.0, key="reforco_preco")
        if st.button("Aplicar Reforço", key="botao_reforco"):
            if novo_montante > 0 and novo_preco > 0:
                antigo_montante = pos["montante"]
                antigo_preco = pos["preco_entrada"]

                total_valor = (antigo_montante / antigo_preco) + (novo_montante / novo_preco)
                novo_total_investido = antigo_montante + novo_montante
                novo_preco_medio = novo_total_investido / total_valor

                pos["montante"] = round(novo_total_investido, 2)
                pos["preco_entrada"] = round(novo_preco_medio, 4)

                posicoes[index] = pos
                guardar_posicoes(posicoes)
                st.success("✅ Reforço aplicado com sucesso!")
                st.rerun()

        # Exportar posições
        csv = df.drop(columns=["Index"]).to_csv(index=False).encode('utf-8')
        st.download_button("📥 Exportar posições", csv, "posicoes.csv", "text/csv")
    else:
        st.info("Ainda não registaste nenhuma posição.")

# ⚠️ NOVO BLOCO para venda manual por input de preço
    if posicoes:
        st.subheader("💸 Vender uma Posição Manualmente")
        index = st.number_input("Seleciona o índice da posição para vender", min_value=0, max_value=len(posicoes)-1, step=1, key="vender_index")
        pos = posicoes[index]

        preco_venda_manual = st.number_input("Preço de venda (USDT)", min_value=0.0, key="preco_manual")
        if st.button("💰 Confirmar Venda Manual"):
            if preco_venda_manual == 0:
                st.warning("⚠️ Introduz um preço válido para a venda.")
            else:
                preco_entrada = pos["preco_entrada"]
                investido = pos["montante"]
                valor_final = preco_venda_manual * (investido / preco_entrada)
                lucro = valor_final - investido
                percent = (lucro / investido) * 100

                registro = {
                    "moeda": pos["moeda"],
                    "data_venda": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "preco_venda": preco_venda_manual,
                    "preco_entrada": preco_entrada,
                    "investido": investido,
                    "valor_final": round(valor_final, 2),
                    "lucro": round(lucro, 2),
                    "percentual": round(percent, 2)
                }

                guardar_venda(registro)
                del posicoes[index]
                guardar_posicoes(posicoes)
                st.success("✅ Venda registada manualmente com sucesso!")
                st.rerun()

# ============================
# 📈 ESTRATÉGIAS
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
            st.info("Nenhuma estratégia registada ainda.")
    except Exception as e:
        st.error(f"❌ Erro ao carregar estratégias: {e}")

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
            st.info("Nenhuma venda registada ainda.")
    except Exception as e:
        st.error(f"❌ Erro ao carregar histórico de vendas: {e}")

# ============================
# 📊 DESEMPENHO DO BOT
# ============================
elif secao == "📊 Desempenho do Bot":
    st.title("📊 Estado e Desempenho do Bot")

    # 🛠️ Progresso do campo 'preco_entrada'
    st.subheader("🛠️ Atualização de 'preco_entrada'")
    try:
        docs = db.collection("historico_previsoes").stream()
        total = 0
        com_preco = 0
        sem_preco = 0

        for doc in docs:
            total += 1
            data = doc.to_dict()
            if "preco_entrada" in data:
                com_preco += 1
            else:
                sem_preco += 1

        if total > 0:
            percent = com_preco / total
            st.write(f"✅ {com_preco} com preço • ❌ {sem_preco} sem preço • Total: {total}")
            st.progress(percent)

            fig, ax = plt.subplots()
            ax.pie([com_preco, sem_preco], labels=["Com preço", "Sem preço"], autopct='%1.1f%%', colors=["#4CAF50", "#F44336"])
            ax.axis("equal")
            st.pyplot(fig)
        else:
            st.info("Nenhum documento encontrado em historico_previsoes.")
    except Exception as e:
        st.error(f"❌ Erro ao verificar progresso de 'preco_entrada': {e}")

    # 🎯 Acertos vs erros do modelo
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
            st.info("Ainda não há vendas registadas.")
    except Exception as e:
        st.error(f"❌ Erro ao carregar histórico de vendas: {e}")

# ============================
# 💸 SIMULAÇÃO DE CAPITAL VIRTUAL
# ===========================
elif secao == "💸 Simulação de Capital Virtual":
    st.title("💸 Painel de Simulação de Capital Virtual")

    try:
        docs = db.collection("simulacoes_vendas").stream()
        vendas = [doc.to_dict() for doc in docs]
    except Exception as e:
        st.error(f"❌ Erro ao carregar simulações: {e}")
        vendas = []

    if vendas:
        df = pd.DataFrame(vendas)
        df["lucro_percentual"] = ((df["preco_venda"] - df["preco_entrada"]) / df["preco_entrada"]) * 100
        df["data"] = pd.to_datetime(df["data_venda"])
        df = df.sort_values("data")
        df["saldo_simulado"] = 1000 + df["lucro"].cumsum()

        saldo_inicial = 1000
        lucro_total = df["lucro"].sum()
        saldo_final = saldo_inicial + lucro_total

        col1, col2 = st.columns(2)
        col1.metric("Orçamento Inicial", f"{saldo_inicial:.2f} USDT")
        col2.metric("Saldo Atual Simulado", f"{saldo_final:.2f} USDT")

        st.markdown("---")
        st.subheader("📊 Vendas Simuladas")
        st.dataframe(df.sort_values("data", ascending=False).style.format({
            "preco_entrada": "{:.2f}",
            "preco_venda": "{:.2f}",
            "lucro": "{:.2f}",
            "lucro_percentual": "{:.2f}%"
        }))

        st.subheader("📈 Lucros por Venda")
        st.line_chart(df.set_index("data")["lucro"])

        st.subheader("📈 Evolução do Saldo Simulado")
        st.line_chart(df.set_index("data")["saldo_simulado"])

        if "encerrado_por" in df.columns:
            st.subheader("📌 Motivo de Encerramento")
            st.bar_chart(df["encerrado_por"].value_counts())

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Exportar CSV", csv, "simulacoes_vendas.csv", "text/csv")
    else:
        st.info("Ainda não foram registadas vendas simuladas.")

