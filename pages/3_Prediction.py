import streamlit as st
import pandas as pd
import numpy as np
import psycopg2
from psycopg2 import sql
from contextlib import closing

# Configuracoes do banco (tá configurado pro meu)
DB_USER = 'postgres'
DB_PASS = 'postgres'
DB_HOST = 'localhost'
DB_NAME = 'microdados'
DB_PORT = 5432
TABLE_NAME = 'dados_enem_consolidado'

# Funcao de conexao
def conectar_db():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        dbname=DB_NAME
    )
    return conn

# Funcao de teste de conexao
def testar_conexao():
    try:
        with closing(conectar_db()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                return True
    except Exception as e:
        st.error(f"Erro na conexão com o banco: {e}")
        return False

# Funcao para buscar gabaritos
def buscar_gabaritos_db(ano):
    query = sql.SQL("""
        SELECT DISTINCT
            {ch}, {ch_g},
            {cn}, {cn_g},
            {lc}, {lc_g},
            {mt}, {mt_g}
        FROM {tabela}
        WHERE {ano_col} = %s
        AND (
            {ch_g} IS NOT NULL OR
            {cn_g} IS NOT NULL OR
            {lc_g} IS NOT NULL OR
            {mt_g} IS NOT NULL
        )
        LIMIT 20;
    """).format(
        ch=sql.Identifier("CO_PROVA_CH"),
        ch_g=sql.Identifier("TX_GABARITO_CH"),
        cn=sql.Identifier("CO_PROVA_CN"),
        cn_g=sql.Identifier("TX_GABARITO_CN"),
        lc=sql.Identifier("CO_PROVA_LC"),
        lc_g=sql.Identifier("TX_GABARITO_LC"),
        mt=sql.Identifier("CO_PROVA_MT"),
        mt_g=sql.Identifier("TX_GABARITO_MT"),
        tabela=sql.Identifier(TABLE_NAME),
        ano_col=sql.Identifier("NU_ANO")
    )
    try:
        with closing(conectar_db()) as conn:
            df = pd.read_sql_query(query.as_string(conn), conn, params=[ano])
        return df
    except Exception as e:
        st.error(f"Erro ao buscar gabaritos no DB: {e}")
        return pd.DataFrame()

class AnalisadorENEM:
    def __init__(self):
        self.mapa_areas = {
            "CH": (1, 45),
            "CN": (46, 90),
            "LC": (91, 135),
            "MT": (136, 180)
        }
        self.areas_nomes = {
            "CH": "Ciências Humanas",
            "CN": "Ciências da Natureza",
            "LC": "Linguagens e Códigos",
            "MT": "Matemática"
        }

    def buscar_gabaritos_db(self, ano):
        return buscar_gabaritos_db(ano)

    def identificar_melhor_prova(self, df_gabs, respostas_usuario):
        if df_gabs.empty:
            return None, 0

        def combinar_gabarito(row):
            completo = []
            for area in ["CH", "CN", "LC", "MT"]:
                col = f"TX_GABARITO_{area}"
                gab = row.get(col)
                if gab is None:
                    completo.extend([None] * 45)
                else:
                    gab_list = list(gab.strip())
                    gab_list = (gab_list + [None]*45)[:45]
                    completo.extend(gab_list)
            return completo

        melhor_score = -1
        melhor_row = None
        melhor_gab_comb = None

        for _, row in df_gabs.iterrows():
            gabarito_comb = combinar_gabarito(row)
            score = 0
            total_comparaveis = 0
            for q_index in range(180):
                user_resp = respostas_usuario.get(q_index+1)
                gab_resp = gabarito_comb[q_index]
                if user_resp is not None and user_resp != "-" and gab_resp is not None:
                    total_comparaveis += 1
                    if user_resp == gab_resp:
                        score += 1
            if score > melhor_score:
                melhor_score = score
                melhor_row = row
                melhor_gab_comb = gabarito_comb

        return melhor_row, melhor_score

    def carregar_medias_db(self, ano, estado=None):
        query = f"""
            SELECT
                AVG("NU_NOTA_CH") AS "MEDIA_CH",
                AVG("NU_NOTA_CN") AS "MEDIA_CN",
                AVG("NU_NOTA_LC") AS "MEDIA_LC",
                AVG("NU_NOTA_MT") AS "MEDIA_MT"
            FROM {TABLE_NAME}
            WHERE "NU_ANO" = %s
            AND "TP_PRESENCA_CH" = 1
            AND "TP_PRESENCA_CN" = 1
            AND "TP_PRESENCA_LC" = 1
            AND "TP_PRESENCA_MT" = 1
        """
        params = [ano]
        if estado:
            query += ' AND "SG_UF_PROVA" = %s'
            params.append(estado)
        try:
            with closing(conectar_db()) as conn:
                df = pd.read_sql_query(query, conn, params=params)
            row = df.iloc[0].to_dict()
            return {k: (None if pd.isna(v) else float(v)) for k, v in row.items()}
        except Exception as e:
            st.error(f"Erro ao carregar médias do DB: {e}")
            return {"MEDIA_CH": None, "MEDIA_CN": None, "MEDIA_LC": None, "MEDIA_MT": None}


    def extrair_respostas_por_area(self, respostas_dict):
        respostas_por_area = {}
        for area, (inicio, fim) in self.mapa_areas.items():
            respostas_area = []
            for q in range(inicio, fim + 1):
                resp = respostas_dict.get(q)
                if resp is not None and resp != "-" and resp in ["A","B","C","D","E"]:
                    respostas_area.append(resp)
                else:
                    respostas_area.append(None)
            respostas_por_area[area] = respostas_area
        return respostas_por_area

    def calcular_acertos(self, respostas_usuario, gabarito_oficial):
        acertos = 0
        total_respondidas = 0
        for resp_usuario, resp_gabarito in zip(respostas_usuario, gabarito_oficial):
            if resp_usuario is not None:
                total_respondidas += 1
                if resp_gabarito is not None and resp_usuario == resp_gabarito:
                    acertos += 1
        return acertos, total_respondidas

    def estimar_nota_tri(self, acertos, total_questoes, media_area):
        if total_questoes == 0:
            return 0
        proporcao_acertos = acertos / total_questoes
        desvio_padrao = 100
        nota_estimada = (media_area if media_area is not None else 500) + (proporcao_acertos - 0.5) * desvio_padrao * 2
        return max(0, min(1000, nota_estimada))

    def analisar_desempenho(self, respostas_dict, ano, cor_prova, estado=None):
        df_gabs = self.buscar_gabaritos_db(ano)
        if df_gabs.empty:
            return {"erro": f"Nenhum gabarito encontrado para o ano {ano} no banco."}

        melhor_row, melhor_score = self.identificar_melhor_prova(df_gabs, respostas_dict)
        if melhor_row is None:
            return {"erro": "Não foi possível identificar um gabarito adequado com as respostas fornecidas."}

        gabarito_oficial = {}
        for area in ["CH","CN","LC","MT"]:
            txt = melhor_row.get(f"TX_GABARITO_{area}")
            if txt is None:
                txt = " " * 45
            txt = (txt.strip() + " " * 45)[:45]
            gabarito_oficial[area] = list(txt)

        medias_nacionais = self.carregar_medias_db(ano, estado=None)
        medias_regionais = self.carregar_medias_db(ano, estado) if estado else None

        respostas_por_area = self.extrair_respostas_por_area(respostas_dict)
        resultados_areas = {}
        for area in ["CH","CN","LC","MT"]:
            respostas = respostas_por_area[area]
            gabarito = gabarito_oficial.get(area, [None]*45)
            acertos, respondidas = self.calcular_acertos(respostas, gabarito)
            percentual = (acertos / 45) * 100 if respondidas > 0 else 0
            key_media_map = {"CH":"MEDIA_CH","CN":"MEDIA_CN","LC":"MEDIA_LC","MT":"MEDIA_MT"}

            media_nacional = medias_nacionais.get(key_media_map[area], None)
            nota_estimada = self.estimar_nota_tri(acertos, 45, media_nacional if media_nacional else 500)
            if medias_regionais:
                media_regional = medias_regionais.get(key_media_map[area], None)
                diferenca_regional = nota_estimada - media_regional if media_regional else None
            else:
                media_regional = None
                diferenca_regional = None
            resultados_areas[area] = {
                "acertos": acertos,
                "total_questoes": 45,
                "respondidas": respondidas,
                "percentual": percentual,
                "nota_estimada": round(nota_estimada,1),
                "media_nacional": round(media_nacional,1) if media_nacional else None,
                "media_regional": round(media_regional,1) if media_regional else None,
                "diferenca_nacional": round(nota_estimada - media_nacional,1) if media_nacional else None,
                "diferenca_regional": round(diferenca_regional,1) if diferenca_regional else None
            }

        total_acertos = sum(r["acertos"] for r in resultados_areas.values())
        nota_geral = sum(r["nota_estimada"] for r in resultados_areas.values()) / 4
        info_prova = {
            "CO_PROVA_CH": melhor_row.get("CO_PROVA_CH"),
            "CO_PROVA_CN": melhor_row.get("CO_PROVA_CN"),
            "CO_PROVA_LC": melhor_row.get("CO_PROVA_LC"),
            "CO_PROVA_MT": melhor_row.get("CO_PROVA_MT"),
            "match_score": int(melhor_score)
        }

        return {
            "resultados_areas": resultados_areas,
            "total_acertos": total_acertos,
            "total_questoes": 180,
            "percentual_geral": round((total_acertos/180)*100,1),
            "nota_geral": round(nota_geral,1),
            "ano": ano,
            "cor_prova": cor_prova,
            "estado": estado,
            "info_prova": info_prova,
            "gabarito_oficial": gabarito_oficial
        }

@st.cache_resource
def get_analisador():
    return AnalisadorENEM()

st.set_page_config(layout="wide")
st.title("Análise de Desempenho Pessoal")

if not testar_conexao():
    st.stop()

#O certo é "-" mas deixei "A" pra testar os resultados (n vou preencher todas as respostas pra testar)
if "respostas" not in st.session_state:
    st.session_state.respostas = {i: "A" for i in range(1, 181)}

if "analise_resultado" not in st.session_state:
    st.session_state.analise_resultado = None

analisador = get_analisador()

st.set_page_config(layout="wide")
st.markdown("""
    <style>
        button[data-testid="stExpandSidebarButton"] { display: none !important; }
        div[data-testid="stToolbar"] {visibility: hidden !important;}
        .gabarito-container { background-color: #2d2d2d; padding: 20px; border-radius: 10px; max-height: 520px; overflow-y: auto; }
        .gabarito-container h3 { color: #fff; position: sticky; top: 0; background:#2d2d2d; padding-top:10px; }
        .stRadio > div { flex-direction: row !important; gap: 6px !important; }
        div[role="radiogroup"] label[data-checked="true"] { background-color: #ff4b4b !important; }
    </style>
""", unsafe_allow_html=True)


if "respostas" not in st.session_state:
    # 
    st.session_state.respostas = {i: "-" for i in range(1, 181)}

if "analise_resultado" not in st.session_state:
    st.session_state.analise_resultado = None

analisador = get_analisador()

st.markdown("## Preencha seu gabarito")
st.markdown('<div class="gabarito-container">', unsafe_allow_html=True)
st.markdown('<h3>Folha de Respostas</h3>', unsafe_allow_html=True)

questoes_por_linha = 5
total_questoes = 180
opt_list = ["-", "A", "B", "C", "D", "E"]

for linha_inicio in range(0, total_questoes, questoes_por_linha):
    cols = st.columns(questoes_por_linha)
    for col_idx in range(questoes_por_linha):
        q_num = linha_inicio + col_idx + 1
        if q_num <= total_questoes:
            with cols[col_idx]:
                resposta_atual = st.session_state.respostas.get(q_num, "-")
                try:
                    index_selecionado = opt_list.index(resposta_atual)
                except ValueError:
                    index_selecionado = 0
                resposta = st.selectbox(
                    f"{q_num:03d}",
                    options=opt_list,
                    index=index_selecionado,
                    key=f"q_{q_num}",
                    label_visibility="visible"
                )
                st.session_state.respostas[q_num] = resposta

st.markdown('</div>', unsafe_allow_html=True)

total_respondidas = sum(1 for r in st.session_state.respostas.values() if r is not None and r != "-")
percentual = (total_respondidas / 180) * 100

st.markdown("---")
st.markdown("### Configurações da Análise")
col_config1, col_config2, col_config3 = st.columns(3)

with col_config1:
    anos_disponiveis = list(range(2014, 2024))
    ano_prova = st.selectbox("Ano da Prova", anos_disponiveis, index=len(anos_disponiveis)-1)

with col_config2:
    cor_prova = st.selectbox("Cor do Caderno (apenas referência)", ["AZUL", "AMARELA", "ROSA", "CINZA"], index=0)

with col_config3:
    estados_br = ["Selecione...", "AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"]
    estado = st.selectbox("Estado (opcional)", estados_br, index=0)
    if estado == "Selecione...":
        estado = None

col1, col2 = st.columns([3,1])

with col1:
    if st.button("Gerar Análise de Desempenho", use_container_width=True, type="primary"):
        if total_respondidas == 0:
            st.error("Você precisa responder pelo menos uma questão")
        else:
            with st.spinner("Analisando seu desempenho..."):
                resultado = analisador.analisar_desempenho(
                    respostas_dict=st.session_state.respostas,
                    ano=ano_prova,
                    cor_prova=cor_prova,
                    estado=estado
                )
                if "erro" in resultado:
                    st.error(resultado["erro"])
                else:
                    st.session_state.analise_resultado = resultado
                    st.success("Análise concluída")

with col2:
    if st.button("Limpar", use_container_width=True):
        st.session_state.respostas = {i: "-" for i in range(1, 181)}
        st.session_state.analise_resultado = None
        st.experimental_rerun()

st.markdown("---")
st.markdown("## Resultados da Análise")

if st.session_state.analise_resultado is not None:
    resultado = st.session_state.analise_resultado
    st.markdown("### Resumo Geral")
    c1,c2,c3,c4 = st.columns(4)
    with c1:
        st.metric("Acertos Totais", f"{resultado['total_acertos']}/180")
    with c2:
        st.metric("Percentual", f"{resultado['percentual_geral']}%")
    with c3:
        st.metric("Nota Geral", f"{resultado['nota_geral']}")
    with c4:
        if resultado['estado']:
            st.metric("Estado", resultado['estado'])
        else:
            st.metric("Comparação", "Nacional")

    st.info(f"Prova escolhida (melhor match): CO_PROVA_CH={resultado['info_prova']['CO_PROVA_CH']}, CO_PROVA_CN={resultado['info_prova']['CO_PROVA_CN']}, CO_PROVA_LC={resultado['info_prova']['CO_PROVA_LC']}, CO_PROVA_MT={resultado['info_prova']['CO_PROVA_MT']} — matches: {resultado['info_prova']['match_score']}")

    st.markdown("### Desempenho por Área")
    for area_code, area_nome in analisador.areas_nomes.items():
        with st.expander(f"{area_nome}", expanded=True):
            res_area = resultado['resultados_areas'][area_code]
            a1,a2,a3,a4 = st.columns(4)
            with a1:
                st.metric("Acertos", f"{res_area['acertos']}/{res_area['total_questoes']}")
            with a2:
                st.metric("Percentual", f"{res_area['percentual']:.1f}%")
            with a3:
                st.metric("Nota Estimada", f"{res_area['nota_estimada']}", delta=f"{res_area['diferenca_nacional']:+.1f} vs nacional" if res_area['diferenca_nacional'] is not None else "")
            with a4:
                if res_area['media_regional']:
                    st.metric("Média Regional", f"{res_area['media_regional']}", delta=f"{res_area['diferenca_regional']:+.1f} você")
                else:
                    st.metric("Média Nacional", f"{res_area['media_nacional']}")
            st.progress(res_area['percentual'] / 100)

    melhor_area = max(resultado['resultados_areas'].items(), key=lambda x: x[1]['nota_estimada'])
    pior_area = min(resultado['resultados_areas'].items(), key=lambda x: x[1]['nota_estimada'])
    colL, colR = st.columns(2)
    with colL:
        st.success(f"Melhor: {analisador.areas_nomes[melhor_area[0]]} — Nota {melhor_area[1]['nota_estimada']}")
    with colR:
        st.warning(f"Pior: {analisador.areas_nomes[pior_area[0]]} — Nota {pior_area[1]['nota_estimada']}")

elif total_respondidas > 0:
    st.info("Configure o ano e cor da prova acima, preencha o gabarito e clique em 'Gerar Análise de Desempenho'")
else:
    st.info("Preencha o gabarito acima para começar sua análise de desempenho")
st.subheader("Teste de conexão com o banco de dados")

if st.button("Testar Conexão"):
    resultado = testar_conexao()
    st.write(resultado)

if st.button("Teste: buscar gabaritos (ano=2019)"):
    df = buscar_gabaritos_db(2019)
    st.write(f"Linhas retornadas: {len(df)}")
    if not df.empty:
        st.dataframe(df.head(20))
