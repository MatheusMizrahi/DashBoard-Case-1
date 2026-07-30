"""
Dashboard estratégico — Lava Rápido Nogueira

Fonte de dados: `Base de dados limpa - Revisada.xlsx` (aba `lavagens`),
enviada pelo mentor do grupo. É o subconjunto de linhas SEM NENHUM valor nulo
em nenhuma coluna (~83 mil de ~198 mil linhas originais) — não usa o
tratamento por imputação/flag que construímos antes (`lavagens_tratada.xlsx`,
ver `tratamento_dados_ausentes.py`), então não existem mais colunas
`_imputado`, `contratou_cera` ou `cliente_identificado`. O arquivo em si não é
alterado (não sobrescrevemos o Excel do mentor); a única filtragem acontece
em `carregar_dados()`, em memória: remove as linhas de domingo (por pedido do
grupo — não é reintroduzida como opção de segmentação, fica sempre fora).

Os filtros de "dia de pico" e "retirada tardia" (`aplicar_segmentacao`) NÃO são
limpeza — são segmentação analítica com toggle próprio. Aparecem nas duas
abas (ligados por padrão na aba POP, desligados/opcionais na Visão Geral) e
nunca alteram `df`/`df_f` em memória, só a view usada nos gráficos de cada
aba. Ver docstring de `aplicar_segmentacao` para o motivo de cada filtro.
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Lava Rápido Nogueira — Painel Estratégico", layout="wide")

ARQUIVO_TRATADO = Path(__file__).parent / "Base de dados limpa - Revisada.xlsx"
ORDEM_DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]
PRODUTOS = ["shampoo_ml", "cera_ml", "pretinho_ml", "aromatizante_ml"]

# Limite de "retirada tardia": limite de NEGÓCIO (comportamento do cliente na
# retirada do carro), não recalculado a cada carga — não confundir com
# limpeza automática por IQR (que este arquivo não tem mais, ver docstring).
LIMITE_RETIRADA_TARDIA_MIN = 45


@st.cache_data
def carregar_dados():
    df = pd.read_excel(ARQUIVO_TRATADO, sheet_name="lavagens")
    df["data"] = pd.to_datetime(df["data"])
    # Pedido do grupo: desconsiderar linhas de domingo (loja não funciona
    # nesse dia) — filtro em memória, o Excel do mentor não é alterado.
    df = df[df["dia_semana"] != "Domingo"].reset_index(drop=True)
    return df


def aplicar_segmentacao(df_base: pd.DataFrame, key_prefix: str, padrao: bool):
    """Widgets de segmentação analítica reutilizados na Visão Geral e na aba POP.

    Dois filtros, sempre combináveis, nunca alteram `df_base` — só retornam
    uma view derivada:

    - "Dia de pico (sábado)": filtro de LINHA (remove a lavagem inteira),
      porque afeta simultaneamente todos os KPIs/gráficos. Domingo já não
      existe na base (removido em `carregar_dados()`), então sábado é o
      único dia de pico que sobra para segmentar.
    - "Retirada tardia (> 45 min)": filtro de VALOR, não de linha — só
      desconta do cálculo de tempo de retirada (`serie_retirada` retornada
      separadamente). As outras métricas do mesmo atendimento (lavagem,
      espera) continuam contando normalmente, porque o tempo até a retirada
      reflete quando o CLIENTE busca o carro, não a eficiência da operação.

    `padrao` controla se os toggles vêm ligados (aba POP, onde a leitura
    "típica" é o objetivo da aba) ou desligados (Visão Geral, onde são
    opcionais). `key_prefix` mantém os widgets das duas abas independentes.
    """
    mask_pico = df_base["dia_semana"] == "Sábado"
    n_pico = int(mask_pico.sum())
    pct_pico = (n_pico / len(df_base) * 100) if len(df_base) else 0.0

    col_a, col_b = st.columns(2)
    excluir_pico = col_a.checkbox(
        f"Excluir dia de pico (sábado) — {n_pico} lavagens ({pct_pico:.1f}%)",
        value=padrao,
        key=f"{key_prefix}_excluir_pico",
        help="Remove a lavagem inteira do sábado desta visão — afeta todos os tempos e KPIs.",
    )
    df_view = df_base[~mask_pico] if excluir_pico else df_base

    mask_retirada_tardia = df_view["tempo_pos_lavagem_ate_retirada_min"] > LIMITE_RETIRADA_TARDIA_MIN
    n_retirada_tardia = int(mask_retirada_tardia.sum())
    pct_retirada_tardia = (n_retirada_tardia / len(df_view) * 100) if len(df_view) else 0.0

    excluir_retirada = col_b.checkbox(
        f"Excluir retiradas tardias (> {LIMITE_RETIRADA_TARDIA_MIN} min) — "
        f"{n_retirada_tardia} casos ({pct_retirada_tardia:.1f}%)",
        value=padrao,
        key=f"{key_prefix}_excluir_retirada",
        help="Desconta só do tempo médio de retirada — não remove a linha, as outras métricas continuam valendo.",
    )
    serie_retirada = (
        df_view.loc[~mask_retirada_tardia, "tempo_pos_lavagem_ate_retirada_min"]
        if excluir_retirada
        else df_view["tempo_pos_lavagem_ate_retirada_min"]
    )
    return df_view, serie_retirada, excluir_pico, excluir_retirada


df = carregar_dados()

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
        "Base enviada pelo mentor do grupo (`Base de dados limpa - Revisada.xlsx`): "
        "contém só as lavagens sem nenhum valor nulo em nenhuma coluna — ou seja, "
        "todo cliente dessa base respondeu NPS e avaliou no Google, então a média "
        "dessas duas métricas aqui reflete só quem respondeu, não a clientela toda. "
        "Linhas de domingo foram descontadas (loja não funciona nesse dia)."
    )

if df_f.empty:
    st.warning("Nenhum registro para os filtros selecionados.")
    st.stop()

aba_geral, aba_pop = st.tabs(["📊 Visão Geral", "🔧 Operação Típica (POP)"])

# ================================================================ ABA GERAL
with aba_geral:
    st.caption(
        "Filtros de segmentação opcionais (mesmos da aba 'Operação Típica'), "
        "desligados por padrão aqui — ligue para ver o impacto dessa segmentação "
        "na visão geral inteira."
    )
    df_view, serie_retirada_geral, excluir_pico_geral, excluir_retirada_geral = aplicar_segmentacao(
        df_f, key_prefix="geral", padrao=False
    )
    if excluir_pico_geral or excluir_retirada_geral:
        st.info(
            f"Segmentação ativa nesta aba: {len(df_view):,} lavagens na visão "
            f"(eram {len(df_f):,} sem segmentação). Todos os gráficos abaixo já refletem isso.".replace(",", ".")
        )

    if df_view.empty:
        st.warning("Nenhum registro sobra com a segmentação atual.")
    else:
        st.divider()

        # ------------------------------------------------------------------ KPIs
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total de lavagens", f"{len(df_view):,}".replace(",", "."))
        col2.metric("Faturamento total", f"R$ {df_view['preco_reais'].sum():,.0f}".replace(",", "."))
        col3.metric("Ticket médio", f"R$ {df_view['preco_reais'].mean():.2f}")
        col4.metric("Tempo médio de lavagem", f"{df_view['tempo_lavagem_total_min'].mean():.1f} min")

        st.divider()

        # ------------------------------------------------------------- faturamento
        st.subheader("Volume e Faturamento")

        serie_mensal = (
            df_view.set_index("data")
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
            "Para os tempos 'normais' de operação com os filtros já ligados por "
            "padrão, veja a aba 'Operação Típica (POP)'."
        )

        tempos_dia = (
            df_view.groupby("dia_semana")[["tempo_lavagem_total_min", "tempo_espera_antes_lavagem_min"]]
            .mean()
            .reindex(ORDEM_DIAS)
            .reset_index()
        )
        volume_dia_total = (
            df_view["dia_semana"].value_counts().reindex(ORDEM_DIAS).rename("lavagens").reset_index()
        )
        volume_dia_total.columns = ["dia_semana", "lavagens"]

        # Quantos dias distintos de cada dia_semana existem na visão atual —
        # necessário pra calcular a média (ex: 8 sábados no período -> total
        # de lavagens de sábado / 8). Só usado se o modo "Média por dia" for
        # selecionado no filtro local abaixo (não altera nenhum outro gráfico).
        dias_distintos = df_view.groupby("dia_semana")["data"].nunique().reindex(ORDEM_DIAS)
        volume_dia_medio = (
            (volume_dia_total.set_index("dia_semana")["lavagens"] / dias_distintos)
            .rename("lavagens")
            .reset_index()
        )

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
        modo_volume_dia = c4.radio(
            "Volume de lavagens por dia da semana:",
            ["Total no período", "Média por dia"],
            horizontal=True,
            key="modo_volume_dia_semana",
        )
        if modo_volume_dia == "Total no período":
            volume_dia_exibir, titulo_volume_dia = volume_dia_total, "Volume total de lavagens por dia da semana"
        else:
            volume_dia_exibir, titulo_volume_dia = volume_dia_medio, "Volume médio de lavagens por dia da semana"
        c4.plotly_chart(
            px.bar(volume_dia_exibir, x="dia_semana", y="lavagens", title=titulo_volume_dia),
            width="stretch",
        )

        # Tempo médio por etapa do processo de lavagem. Como usa df_view (já
        # recortado pelo filtro de Período + segmentação ativa), o
        # comportamento pedido sai de graça: 1 dia selecionado -> média das
        # lavagens daquele dia; vários dias -> média do período inteiro.
        if data_inicio == data_fim:
            legenda_periodo = f"{data_inicio.strftime('%d/%m/%Y')} ({len(df_view)} lavagens nesse dia)"
        else:
            n_dias = df_view["data"].dt.date.nunique()
            legenda_periodo = (
                f"{data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')} "
                f"({n_dias} dias, {len(df_view)} lavagens)"
            )

        ETAPAS = {
            "t_teto_vidros_min": "Teto / Vidros",
            "t_capo_parabrisa_min": "Capô / Parabrisa",
            "t_laterais_portas_min": "Laterais / Portas",
            "t_traseira_min": "Traseira",
            "t_rodas_pneus_min": "Rodas / Pneus",
            "t_interior_min": "Interior",
        }
        tempo_etapas = (
            df_view[list(ETAPAS.keys())]
            .mean()
            .rename(index=ETAPAS)
            .reset_index()
        )
        tempo_etapas.columns = ["etapa", "tempo_medio_min"]

        # Tempo médio por fase macro do atendimento (espera -> lavagem ->
        # pós-lavagem até retirada -> até pagamento). A fase de retirada usa
        # `serie_retirada_geral` (não df_view diretamente) para respeitar o
        # filtro de retirada tardia, que é column-level e não deve afetar as
        # demais fases.
        tempo_fases = pd.DataFrame({
            "fase": [
                "Espera antes da lavagem",
                "Lavagem (total)",
                "Pós-lavagem até retirada",
                "Até pagamento",
            ],
            "tempo_medio_min": [
                df_view["tempo_espera_antes_lavagem_min"].mean(),
                df_view["tempo_lavagem_total_min"].mean(),
                serie_retirada_geral.mean(),
                df_view["tempo_ate_pagamento_min"].mean(),
            ],
        })

        c_etapas, c_fases = st.columns(2)
        c_etapas.plotly_chart(
            px.bar(
                tempo_etapas,
                x="etapa",
                y="tempo_medio_min",
                text_auto=".1f",
                title=f"Tempo médio por etapa da lavagem — {legenda_periodo}",
                labels={"etapa": "Etapa", "tempo_medio_min": "Tempo médio (min)"},
            ),
            width="stretch",
        )
        c_fases.plotly_chart(
            px.bar(
                tempo_fases,
                x="fase",
                y="tempo_medio_min",
                text_auto=".1f",
                title=f"Tempo médio por fase do atendimento — {legenda_periodo}",
                labels={"fase": "Fase", "tempo_medio_min": "Tempo médio (min)"},
            ),
            width="stretch",
        )

        # -------------------------------------------------------------- pagamento
        st.subheader("Financeiro: mix de pagamento")

        mix_pag = df_view["metodo_pagamento"].value_counts().rename("quantidade").reset_index()
        mix_pag.columns = ["metodo_pagamento", "quantidade"]

        mix_pag_ano = (
            df_view.groupby([df_view["data"].dt.year.rename("ano"), "metodo_pagamento"])
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
            df_view.groupby(df_view["data"].dt.year.rename("ano"))
            .agg(
                nps_medio=("nps_cliente", "mean"),
                google_medio=("nota_google", "mean"),
            )
            .reset_index()
        )

        c7, c8 = st.columns(2)
        c7.plotly_chart(
            px.line(sat_ano, x="ano", y="nps_medio", title="NPS médio por ano (escala 0-10)"),
            width="stretch",
        )
        c8.plotly_chart(
            px.line(sat_ano, x="ano", y="google_medio", title="Nota Google média por ano (escala 1-5)"),
            width="stretch",
        )

        st.caption(
            "Lembrete: esta base só contém lavagens sem nenhum nulo — a média de NPS/Nota "
            "Google aqui é sobre quem respondeu, não sobre a clientela toda (ver 'Sobre os dados')."
        )

        # --------------------------------------------------------------- produtos
        st.subheader("Produtos: consumo de insumos e mix de veículos")

        consumo = df_view.groupby("tipo_carro")[PRODUTOS].mean().reset_index()
        dist_carro = df_view["tipo_carro"].value_counts().rename("quantidade").reset_index()
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
        "ligados por padrão só nesta aba (na Visão Geral eles existem também, mas "
        "desligados/opcionais)."
    )

    df_pop, serie_retirada_pop, excluir_pico, excluir_retirada = aplicar_segmentacao(
        df_f, key_prefix="pop", padrao=True
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
