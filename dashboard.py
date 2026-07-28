"""
Dashboard estratégico — Lava Rápido Nogueira

Lê a planilha original e aplica, em memória, as mesmas duas correções
documentadas em `limpeza.ipynb`:
  1. remove as lavagens registradas aos domingos (loja não funciona nesse dia);
  2. preenche `cera_ml` nulo com 0 (assume "não usou cera").
Todas as outras colunas com nulo são mantidas como estão (ver `limpeza.ipynb`
Seção 8 para a justificativa de cada uma) — o dashboard não inventa dado.
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Lava Rápido Nogueira — Painel Estratégico", layout="wide")

ARQUIVO_ORIGINAL = Path(__file__).parent / "Base de Dados - Lava Rapido Nogueira.xlsx"
ORDEM_DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]
PRODUTOS = ["shampoo_ml", "cera_ml", "pretinho_ml", "aromatizante_ml"]


@st.cache_data
def carregar_dados():
    df = pd.read_excel(ARQUIVO_ORIGINAL, sheet_name="lavagens")
    df["data"] = pd.to_datetime(df["data"])

    # Seção 5 do notebook: loja não abre aos domingos -> registros inconsistentes
    df = df[df["dia_semana"] != "Domingo"].reset_index(drop=True)

    # Seção 8 do notebook: cera é opcional, nulo == "não usou"
    df["cera_ml"] = df["cera_ml"].fillna(0)

    return df


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

tipos_carro_sel = st.sidebar.multiselect(
    "Tipo de carro", sorted(df["tipo_carro"].dropna().unique())
)
metodos_pag_sel = st.sidebar.multiselect(
    "Método de pagamento", sorted(df["metodo_pagamento"].dropna().unique())
)
dias_semana_sel = st.sidebar.multiselect("Dia da semana", ORDEM_DIAS)
cnpj_sel = st.sidebar.multiselect(
    "CNPJ / Razão social", sorted(df["cnpj_receita"].dropna().unique())
)

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
        "Domingos já removidos da base inteira (loja fechada). "
        "`cera_ml` nulo tratado como 0 (não usou). "
        "NPS e Nota Google são opcionais para o cliente — o painel sempre "
        "mostra a cobertura (% que respondeu) ao lado da média, para não "
        "comparar períodos com adesão muito diferente."
    )

if df_f.empty:
    st.warning("Nenhum registro para os filtros selecionados.")
    st.stop()

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

mix_pag = df_f["metodo_pagamento"].value_counts(dropna=False).rename("quantidade").reset_index()
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
        nps_cobertura=("nps_cliente", lambda s: s.notna().mean() * 100),
        google_medio=("nota_google", "mean"),
        google_cobertura=("nota_google", lambda s: s.notna().mean() * 100),
    )
    .reset_index()
)

c7, c8 = st.columns(2)
fig_nps = px.line(sat_ano, x="ano", y="nps_medio", title="NPS médio por ano (escala 0-10)")
fig_nps.add_bar(
    x=sat_ano["ano"], y=sat_ano["nps_cobertura"], name="% cobertura", yaxis="y2", opacity=0.3
)
fig_nps.update_layout(yaxis2=dict(overlaying="y", side="right", title="% cobertura", range=[0, 100]))
c7.plotly_chart(fig_nps, width="stretch")

fig_google = px.line(sat_ano, x="ano", y="google_medio", title="Nota Google média por ano (escala 1-5)")
fig_google.add_bar(
    x=sat_ano["ano"], y=sat_ano["google_cobertura"], name="% cobertura", yaxis="y2", opacity=0.3
)
fig_google.update_layout(yaxis2=dict(overlaying="y", side="right", title="% cobertura", range=[0, 100]))
c8.plotly_chart(fig_google, width="stretch")

st.caption(
    "As barras translúcidas mostram o % de clientes que responderam naquele ano — "
    "cobertura baixa (comum em anos antigos) torna a média menos confiável."
)

# --------------------------------------------------------------- produtos
st.subheader("Produtos: consumo de insumos e mix de veículos")

consumo = df_f.groupby("tipo_carro")[PRODUTOS].mean().reset_index()
dist_carro = df_f["tipo_carro"].value_counts(dropna=False).rename("quantidade").reset_index()
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
