"""
Dashboard estratégico — Lava Rápido Nogueira

Fonte de dados: `lavagens_tratada.xlsx`, já com o tratamento de nulos aplicado
(ver `tratamento_dados_ausentes.py` / relatório correspondente) — domingos
removidos, `cera_ml` e demais colunas MCAR/MAR tratadas, sem valores nulos
restantes.

Este arquivo aplica, além disso, apenas UMA limpeza automática adicional:
outliers de registro (não segmentação analítica) em `tempo_lavagem_total_min`
e `tempo_ate_pagamento_min` via IQR padrão — ver `limpar_ruido_de_registro()`.

Os filtros de "dia de pico" e "retirada tardia" NÃO são limpeza — são
segmentação analítica com toggle próprio, vivem só na aba "Operação Típica
(POP)" e nunca alteram `df` em memória, só a view usada nos gráficos daquela
aba. Ver comentários na seção da aba POP para o motivo de cada um.
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Lava Rápido Nogueira — Painel Estratégico", layout="wide")

ARQUIVO_TRATADO = Path(__file__).parent / "lavagens_tratada.xlsx"
ORDEM_DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]
PRODUTOS = ["shampoo_ml", "cera_ml", "pretinho_ml", "aromatizante_ml"]

# Limite de "retirada tardia": IQR (1.5x) calculado só sobre os valores
# OBSERVADOS de tempo_pos_lavagem_ate_retirada_min (excluindo os ~17,3% que
# foram imputados pela mediana no tratamento de nulos) = 45 min. Fixo aqui
# porque é um limite de negócio (comportamento do cliente), não estatístico
# recalculado a cada carga — não confundir com limpeza automática por IQR.
LIMITE_RETIRADA_TARDIA_MIN = 45


def limpar_ruido_de_registro(df: pd.DataFrame) -> pd.DataFrame:
    """Remove linhas com erro/ruído genuíno de registro.

    Só se aplica a tempo_lavagem_total_min e tempo_ate_pagamento_min: ambas
    têm baixo volume de valores fora da faixa (~2,2% e ~0,1%) SEM associação
    com nenhuma variável observada (dia, funcionário, método de pagamento) —
    ou seja, é ruído aleatório de digitação/medição, não um padrão
    operacional real. Por isso é tratado como limpeza de fato, ligado por
    padrão, sem toggle na interface.

    IMPORTANTE — isso é DIFERENTE de tempo_espera_antes_lavagem_min e
    tempo_pos_lavagem_ate_retirada_min: aquelas duas têm um padrão claro por
    trás (dia de pico e comportamento do cliente na retirada), então tratar
    como "ruído" e limpar automaticamente seria apagar informação real sobre
    a operação. Por isso elas viram filtro de segmentação explícito na aba
    "Operação Típica", nunca limpeza automática. Não simplificar isso para
    um único bloco de "remoção de outliers" genérico.
    """
    limites = {}
    mask_valida = pd.Series(True, index=df.index)
    for coluna in ["tempo_lavagem_total_min", "tempo_ate_pagamento_min"]:
        q1, q3 = df[coluna].quantile(0.25), df[coluna].quantile(0.75)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        limites[coluna] = (lo, hi)
        mask_valida &= df[coluna].between(lo, hi)
    return df[mask_valida].reset_index(drop=True)


@st.cache_data
def carregar_dados():
    df = pd.read_excel(ARQUIVO_TRATADO, sheet_name="lavagens_tratada")
    df["data"] = pd.to_datetime(df["data"])
    linhas_antes = len(df)
    df = limpar_ruido_de_registro(df)
    linhas_removidas_ruido = linhas_antes - len(df)
    return df, linhas_removidas_ruido


df, linhas_removidas_ruido = carregar_dados()

st.title("🚗 Lava Rápido Nogueira — Painel Estratégico")

# ------------------------------------------------------------------ filtros
st.sidebar.header("Filtros")

data_min, data_max = df["data"].min().date(), df["data"].max().date()
inicio_padrao = max(data_min, pd.Timestamp("2018-01-01").date())

intervalo = st.sidebar.date_input(
    "Período",
    value=(inicio_padrao, data_max),
    min_value=data_min,
    max_value=data_max,
)
if len(intervalo) != 2:
    st.info("Selecione uma data inicial e uma final para continuar.")
    st.stop()
data_inicio, data_fim = intervalo

tipos_carro_sel = st.sidebar.multiselect("Tipo de carro", sorted(df["tipo_carro"].unique()))
metodos_pag_sel = st.sidebar.multiselect("Método de pagamento", sorted(df["metodo_pagamento"].unique()))
dias_semana_sel = st.sidebar.multiselect("Dia da semana", ORDEM_DIAS)
cnpj_sel = st.sidebar.multiselect("CNPJ / Razão social", sorted(df["cnpj_receita"].unique()))

mask = (df["data"].dt.date >= data_inicio) & (df["data"].dt.date <= data_fim)
if tipos_carro_sel:
    mask &= df["tipo_carro"].isin(tipos_carro_sel)
if metodos_pag_sel:
    mask &= df["metodo_pagamento"].isin(metodos_pag_sel)
if dias_semana_sel:
    mask &= df["dia_semana"].isin(dias_semana_sel)
if cnpj_sel:
    mask &= df["cnpj_receita"].isin(cnpj_sel)

df_f = df[mask]

with st.sidebar.expander("Sobre os dados"):
    st.caption(
        f"Base já tratada (`lavagens_tratada.xlsx`): domingos removidos, "
        f"nulos tratados (imputação por modelo, mediana ou categoria explícita "
        f"'não registrado'/'cliente_nao_identificado' conforme o caso). "
        f"{linhas_removidas_ruido} linhas adicionais removidas aqui por ruído de "
        f"registro em tempo_lavagem_total_min/tempo_ate_pagamento_min (IQR). "
        f"NPS e Nota Google têm grande parte dos valores estimados por modelo "
        f"(não são resposta real do cliente) — colunas `nps_cliente_imputado` e "
        f"`nota_google_imputado` marcam quais. As barras translúcidas nos "
        f"gráficos de satisfação mostram o % realmente observado."
    )

if df_f.empty:
    st.warning("Nenhum registro para os filtros selecionados.")
    st.stop()

aba_geral, aba_pop = st.tabs(["📊 Visão Geral", "🔧 Operação Típica (POP)"])

# ================================================================ ABA GERAL
with aba_geral:
    # ------------------------------------------------------------------ KPIs
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de lavagens", f"{len(df_f):,}".replace(",", "."))
    col2.metric("Faturamento total", f"R$ {df_f['preco_reais'].sum():,.0f}".replace(",", "."))
    col3.metric("Ticket médio", f"R$ {df_f['preco_reais'].mean():.2f}")
    col4.metric("Tempo médio de lavagem", f"{df_f['tempo_lavagem_total_min'].mean():.1f} min")

    st.divider()

    # ------------------------------------------------------------- faturamento
    st.subheader("Volume e Faturamento")

    serie_mensal = (
        df_f.set_index("data")
        .resample("MS")
        .agg(faturamento=("preco_reais", "sum"), lavagens=("id_lavagem", "count"))
        .reset_index()
    )

    c1, c2 = st.columns(2)
    c1.plotly_chart(
        px.line(serie_mensal, x="data", y="faturamento", title="Faturamento mensal (R$)"),
        width="stretch",
    )
    c2.plotly_chart(
        px.line(serie_mensal, x="data", y="lavagens", title="Volume de lavagens por mês"),
        width="stretch",
    )

    # ------------------------------------------------------------- operacional
    st.subheader("Operacional: tempos e volume por dia da semana")
    st.caption(
        "Visão completa (todos os dias). Para os tempos 'normais' de operação, "
        "sem o efeito do dia de pico, veja a aba 'Operação Típica (POP)'."
    )

    tempos_dia = (
        df_f.groupby("dia_semana")[["tempo_lavagem_total_min", "tempo_espera_antes_lavagem_min"]]
        .mean()
        .reindex(ORDEM_DIAS)
        .reset_index()
    )
    volume_dia = (
        df_f["dia_semana"].value_counts().reindex(ORDEM_DIAS).rename("lavagens").reset_index()
    )
    volume_dia.columns = ["dia_semana", "lavagens"]

    c3, c4 = st.columns(2)
    c3.plotly_chart(
        px.bar(
            tempos_dia,
            x="dia_semana",
            y=["tempo_lavagem_total_min", "tempo_espera_antes_lavagem_min"],
            barmode="group",
            title="Tempo médio (min) por dia da semana",
        ),
        width="stretch",
    )
    c4.plotly_chart(
        px.bar(volume_dia, x="dia_semana", y="lavagens", title="Volume de lavagens por dia da semana"),
        width="stretch",
    )

    # -------------------------------------------------------------- pagamento
    st.subheader("Financeiro: mix de pagamento")

    mix_pag = df_f["metodo_pagamento"].value_counts().rename("quantidade").reset_index()
    mix_pag.columns = ["metodo_pagamento", "quantidade"]

    mix_pag_ano = (
        df_f.groupby([df_f["data"].dt.year.rename("ano"), "metodo_pagamento"])
        .size()
        .reset_index(name="quantidade")
    )

    c5, c6 = st.columns(2)
    c5.plotly_chart(
        px.pie(mix_pag, names="metodo_pagamento", values="quantidade", title="Distribuição por método de pagamento"),
        width="stretch",
    )
    c6.plotly_chart(
        px.area(
            mix_pag_ano,
            x="ano",
            y="quantidade",
            color="metodo_pagamento",
            groupnorm="fraction",
            title="Evolução do mix de pagamento por ano",
        ),
        width="stretch",
    )

    # ------------------------------------------------------------- satisfação
    st.subheader("Satisfação do cliente")

    sat_ano = (
        df_f.groupby(df_f["data"].dt.year.rename("ano"))
        .agg(
            nps_medio=("nps_cliente", "mean"),
            nps_cobertura=("nps_cliente_imputado", lambda s: (~s).mean() * 100),
            google_medio=("nota_google", "mean"),
            google_cobertura=("nota_google_imputado", lambda s: (~s).mean() * 100),
        )
        .reset_index()
    )

    c7, c8 = st.columns(2)
    fig_nps = px.line(sat_ano, x="ano", y="nps_medio", title="NPS médio por ano (escala 0-10)")
    fig_nps.add_bar(
        x=sat_ano["ano"], y=sat_ano["nps_cobertura"], name="% observado (não imputado)", yaxis="y2", opacity=0.3
    )
    fig_nps.update_layout(yaxis2=dict(overlaying="y", side="right", title="% observado", range=[0, 100]))
    c7.plotly_chart(fig_nps, width="stretch")

    fig_google = px.line(sat_ano, x="ano", y="google_medio", title="Nota Google média por ano (escala 1-5)")
    fig_google.add_bar(
        x=sat_ano["ano"], y=sat_ano["google_cobertura"], name="% observado (não imputado)", yaxis="y2", opacity=0.3
    )
    fig_google.update_layout(yaxis2=dict(overlaying="y", side="right", title="% observado", range=[0, 100]))
    c8.plotly_chart(fig_google, width="stretch")

    st.caption(
        "As barras translúcidas mostram o % de linhas com valor REALMENTE observado "
        "(não estimado por modelo) — quanto menor, mais a média depende de imputação "
        "estatística em vez do que o cliente de fato respondeu."
    )

    # --------------------------------------------------------------- produtos
    st.subheader("Produtos: consumo de insumos e mix de veículos")

    consumo = df_f.groupby("tipo_carro")[PRODUTOS].mean().reset_index()
    dist_carro = df_f["tipo_carro"].value_counts().rename("quantidade").reset_index()
    dist_carro.columns = ["tipo_carro", "quantidade"]

    c9, c10 = st.columns(2)
    c9.plotly_chart(
        px.bar(consumo, x="tipo_carro", y=PRODUTOS, barmode="group", title="Consumo médio (ml) por tipo de carro"),
        width="stretch",
    )
    c10.plotly_chart(
        px.pie(dist_carro, names="tipo_carro", values="quantidade", title="Distribuição de lavagens por tipo de carro"),
        width="stretch",
    )

# ================================================================== ABA POP
with aba_pop:
    st.caption(
        "Visão para apoiar a definição do POP (Procedimento Operacional Padrão): "
        "os dois filtros abaixo excluem da leitura o que não representa a operação "
        "'normal' do dia a dia. São filtros de SEGMENTAÇÃO ANALÍTICA, não limpeza — "
        "ligados por padrão só nesta aba; a aba 'Visão Geral' nunca é afetada por eles."
    )

    # --- Filtro 1 (nível de LINHA — afeta todos os KPIs/gráficos desta aba):
    # Sábado é o único dia de pico que sobrou na base (domingo já foi removido
    # na limpeza anterior). Concentra ~30% do volume e ~98% dos horários de
    # espera estatisticamente atípicos — incluir esse dia empurra a média de
    # "tempo normal de espera" para cima de forma enganosa para fins de POP.
    mask_sabado = df_f["dia_semana"] == "Sábado"
    n_sabado = int(mask_sabado.sum())
    pct_sabado = (n_sabado / len(df_f) * 100) if len(df_f) else 0.0

    excluir_pico = st.checkbox(
        f"Excluir dia de pico (sábado) — {n_sabado} lavagens ({pct_sabado:.1f}% da visão atual)",
        value=True,
        key="pop_excluir_pico",
        help="Remove a lavagem inteira do sábado da visão desta aba — afeta todos os tempos e KPIs abaixo.",
    )
    df_pop = df_f[~mask_sabado] if excluir_pico else df_f

    # --- Filtro 2 (nível de VALOR — só afeta a métrica de retirada, não a linha
    # inteira): tempo até a retirada reflete quando o CLIENTE busca o carro, não
    # a eficiência da lavagem em si. Acima de 45 min (limite do IQR calculado
    # sobre os valores observados dessa coluna) é comportamento do cliente, não
    # atraso operacional — por isso só é descontado do cálculo de tempo de
    # retirada, e as demais métricas do mesmo atendimento (lavagem, espera)
    # continuam contando normalmente.
    mask_retirada_tardia = df_pop["tempo_pos_lavagem_ate_retirada_min"] > LIMITE_RETIRADA_TARDIA_MIN
    n_retirada_tardia = int(mask_retirada_tardia.sum())
    pct_retirada_tardia = (n_retirada_tardia / len(df_pop) * 100) if len(df_pop) else 0.0

    excluir_retirada = st.checkbox(
        f"Excluir retiradas tardias (> {LIMITE_RETIRADA_TARDIA_MIN} min) — "
        f"{n_retirada_tardia} casos ({pct_retirada_tardia:.1f}% da visão atual)",
        value=True,
        key="pop_excluir_retirada",
        help="Desconta só do tempo médio de retirada — não remove a linha, as outras métricas do mesmo atendimento continuam valendo.",
    )
    serie_retirada_pop = (
        df_pop.loc[~mask_retirada_tardia, "tempo_pos_lavagem_ate_retirada_min"]
        if excluir_retirada
        else df_pop["tempo_pos_lavagem_ate_retirada_min"]
    )

    if df_pop.empty:
        st.warning("Nenhum registro sobra com os filtros/segmentações atuais.")
    else:
        st.caption(f"Visão típica atual: {len(df_pop):,} lavagens".replace(",", "."))
        st.divider()

        algum_filtro_ativo = excluir_pico or excluir_retirada

        tempo_lavagem_tipico = df_pop["tempo_lavagem_total_min"].mean()
        tempo_espera_tipico = df_pop["tempo_espera_antes_lavagem_min"].mean()
        tempo_retirada_tipico = serie_retirada_pop.mean()

        tempo_lavagem_completo = df_f["tempo_lavagem_total_min"].mean()
        tempo_espera_completo = df_f["tempo_espera_antes_lavagem_min"].mean()
        tempo_retirada_completo = df_f["tempo_pos_lavagem_ate_retirada_min"].mean()

        colp1, colp2, colp3 = st.columns(3)
        colp1.metric("Tempo médio de lavagem", f"{tempo_lavagem_tipico:.1f} min")
        colp2.metric("Tempo médio de espera", f"{tempo_espera_tipico:.1f} min")
        colp3.metric("Tempo médio até retirada", f"{tempo_retirada_tipico:.1f} min")
        if algum_filtro_ativo:
            colp1.caption(f"Visão completa (sem segmentação): {tempo_lavagem_completo:.1f} min")
            colp2.caption(f"Visão completa (sem segmentação): {tempo_espera_completo:.1f} min")
            colp3.caption(f"Visão completa (sem segmentação): {tempo_retirada_completo:.1f} min")

        st.divider()

        c11, c12 = st.columns(2)
        c11.plotly_chart(
            px.histogram(
                df_pop, x="tempo_lavagem_total_min", nbins=40,
                title="Distribuição do tempo de lavagem — visão típica",
            ).add_vline(x=tempo_lavagem_tipico, line_dash="dash", annotation_text="média"),
            width="stretch",
        )

        tempo_func = (
            df_pop.groupby("funcionario_lavagem")["tempo_lavagem_total_min"]
            .mean()
            .sort_values()
            .reset_index()
        )
        c12.plotly_chart(
            px.bar(
                tempo_func, x="tempo_lavagem_total_min", y="funcionario_lavagem", orientation="h",
                title="Tempo médio de lavagem por funcionário — visão típica",
                height=max(400, len(tempo_func) * 18),
            ),
            width="stretch",
        )
