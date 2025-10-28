import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# --- Estilo customizado ---
st.markdown("""
    <style>
        body { background-color: #111111; }
        .stTabs [role="tablist"] button {
            font-size: 16px;
            font-weight: bold;
        }
        div[data-testid="stMetricValue"] {
            font-size: 32px;
            font-weight: bold;
        }
        .big-button button {
            font-size: 18px;
            font-weight: bold;
            padding: 0.6em 2em;
            border-radius: 10px;
        }
        .stRadio > label {
            font-weight: bold;
        }
    </style>
""", unsafe_allow_html=True)

st.title("📈 Predição de Desempenho")

# Mock de previsão
def predict_notas(sexo=None, renda=None, esc_pai=None, esc_mae=None, escola=None, idade=None):
    np.random.seed(42)
    return {
        "Linguagens e Códigos": np.random.randint(400, 800),
        "Ciências Humanas": np.random.randint(400, 800),
        "Ciências da Natureza": np.random.randint(400, 800),
        "Matemática": np.random.randint(400, 800),
        "Redação": np.random.randint(400, 1000),
    }

# Inicializa session_state
if "notas" not in st.session_state:
    st.session_state.notas = predict_notas()

default_values = {
    "sexo": "Masculino",
    "idade": 20,
    "renda": "1-3 SM",
    "esc_pai": "Ensino Médio",
    "esc_mae": "Superior",
    "escola": "Pública",
    "internet": "Sim",
    "computador": "Sim"
}

for k, v in default_values.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Tabs
tab1, tab2 = st.tabs(["🎯 Simulação de Resultado", "📌 Variáveis Importantes"])

# ================= TAB 1 =================
with tab1:
    st.info("Preencha os campos socioeconômicos e veja a previsão dinâmica de desempenho em cada área do ENEM.")

    # --- Cards com métricas ---
    st.subheader("📊 Resultado da Predição")
    cards_placeholder = st.empty()

    def render_cards():
        with cards_placeholder:
            cols = st.columns(5)
            for (area, nota), col in zip(st.session_state.notas.items(), cols):
                col.metric(area, nota)

    # Render inicial (sempre uma vez só)
    render_cards()

    # --- Formulário ---
    st.subheader("🧑‍🎓 Dados do Participante")
    with st.form("prediction_form"):
        sexo = st.radio("Sexo", ["Masculino", "Feminino", "Prefiro não informar"],
                        horizontal=True, index=["Masculino", "Feminino", "Prefiro não informar"].index(st.session_state.sexo))

        idade = st.slider("Idade", 0, 100, st.session_state.idade)

        renda = st.radio("Renda Familiar", ["Até 1 SM", "1-3 SM", "3-5 SM", "Mais de 5 SM"],
                        horizontal=True, index=["Até 1 SM", "1-3 SM", "3-5 SM", "Mais de 5 SM"].index(st.session_state.renda))

        col1, col2 = st.columns(2)
        with col1:
            esc_pai = st.select_slider(
                "Escolaridade do Pai",
                options=["Fundamental", "Ensino Médio", "Superior", "Pós-graduação", "Não informado"],
                value=st.session_state.esc_pai
            )
        with col2:
            esc_mae = st.select_slider(
                "Escolaridade da Mãe",
                options=["Fundamental", "Ensino Médio", "Superior", "Pós-graduação", "Não informado"],
                value=st.session_state.esc_mae
            )

        escola = st.radio("Tipo da Escola", ["Pública", "Privada", "Federal"],
                        horizontal=True, index=["Pública", "Privada", "Federal"].index(st.session_state.escola))

        col1, col2 = st.columns(2)
        with col1:
            internet = st.radio("Possui acesso à Internet?", ["Sim", "Não"],
                                horizontal=True, index=["Sim", "Não"].index(st.session_state.internet))
        with col2:
            computador = st.radio("Possui computador?", ["Sim", "Não"],
                                horizontal=True, index=["Sim", "Não"].index(st.session_state.computador))

        col1, col2 = st.columns(2)
        with col1:
            limpar = st.form_submit_button("🗑️ Limpar")
        with col2:
            submitted = st.form_submit_button("📊 Gerar Nova Previsão")

    # --- Ações dos botões ---
    if submitted:
        st.session_state.update({
            "sexo": sexo,
            "idade": idade,
            "renda": renda,
            "esc_pai": esc_pai,
            "esc_mae": esc_mae,
            "escola": escola,
            "internet": internet,
            "computador": computador,
        })
        st.session_state.notas = predict_notas(sexo, renda, esc_pai, esc_mae, escola, idade)
        render_cards()  # re-renderiza no mesmo placeholder

    if limpar:
        for k, v in default_values.items():
            st.session_state[k] = v
        st.session_state.notas = predict_notas()
        st.rerun()

    # --- Gráfico ---
    st.subheader("📈 Visualização Gráfica")
    df_notas = pd.DataFrame({
        "Área": list(st.session_state.notas.keys()),
        "Nota Prevista": list(st.session_state.notas.values())
    })
    fig = px.bar(df_notas, x="Área", y="Nota Prevista", text="Nota Prevista",
                color="Área", title="Notas Previstas por Área do ENEM")
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)


# ================= TAB 2 =================
with tab2:
    st.info("Veja as variáveis que mais impactam no resultado do modelo.")

    variaveis = [
        {"nome": "Renda Familiar", "descricao": "A renda está fortemente relacionada ao acesso a materiais de estudo e cursos preparatórios."},
        {"nome": "Tipo de Escola", "descricao": "Estudantes de escolas privadas, em média, têm acesso a mais recursos de aprendizagem."},
        {"nome": "Escolaridade da Mãe", "descricao": "Pesquisas indicam que o nível de escolaridade da mãe tem alta correlação com o desempenho escolar."},
        {"nome": "Sexo", "descricao": "Diferenças de desempenho entre homens e mulheres são observadas em algumas áreas do ENEM."},
    ]

    cols = st.columns(2)

    for i, var in enumerate(variaveis):
        # Criar uma função dialog única para cada variável
        @st.dialog(var["nome"])
        def abrir_dialogo(v=var):
            st.markdown(f"### {v['nome']}")
            st.write(v["descricao"])
            st.info("🔎 Aqui futuramente poderemos mostrar gráficos explicativos do impacto desta variável.")
            # Exemplo de gráfico fake
            st.bar_chart({"Impacto": np.random.randint(1, 100, size=5)})

        with cols[i % 2]:
            if st.button(var["nome"], use_container_width=True, key=f"btn_{i}"):
                abrir_dialogo()