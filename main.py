import streamlit as st
import pandas as pd
import plotly.express as px

#https://wdmkkd6ps4-cmd.github.io/Asker-dashbord/

# Sidekonfigurasjon
st.set_page_config(page_title="Kø og forsinkelser - Asker", layout="wide")

# Custom CSS for sidebar styling
st.markdown("""
<style>
    [data-testid="stSidebar"] {
        background-color: #e8e8e8;
    }
    .sidebar-header {
        background-color: #2c5f7c;
        color: white;
        padding: 15px;
        margin: -1rem -1rem 1rem -1rem;
        font-size: 1.2rem;
        font-weight: bold;
    }
    [data-testid="stSidebar"] .stRadio > label {
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_data():
    """Last inn og preprosesser data"""
    df = pd.read_csv(
        "data/inndata_asker_ko.csv",
        sep=";",
        decimal=",",
        encoding="utf-8-sig"
    )

    # Rensk kolonnenavn for eventuelle usynlige tegn
    df.columns = df.columns.str.strip().str.replace('\ufeff', '')

    # Normaliser kolonnenavn til lowercase
    df.columns = df.columns.str.lower()

    # Konverter dato - håndter både ISO-format og norsk format
    if df["dato"].dtype == 'object' and df["dato"].str.contains(",").any():
        # Norsk format: 16,10,2025
        df["dato"] = df["dato"].str.replace(",", ".")
        df["dato"] = pd.to_datetime(df["dato"], format="%d.%m.%Y")
    else:
        # ISO format: 2025-10-16
        df["dato"] = pd.to_datetime(df["dato"])

    # Håndter tomme verdier i Forsinkelser
    df["forsinkelser"] = pd.to_numeric(df["forsinkelser"], errors="coerce")

    return df


# Last data
df = load_data()

# Sidebar
with st.sidebar:
    st.markdown('<div class="sidebar-header">Velg gruppering</div>', unsafe_allow_html=True)

    # Multiselect for strekninger
    alle_strekninger = sorted(df["stop_name"].unique().tolist())
    valgte_strekninger = st.multiselect(
        "Strekning",
        options=alle_strekninger,
        default=[],
        placeholder="Alle strekninger"
    )

    st.markdown("---")

    # Radio buttons for valg av diagram (Kø / Forsinkelser)
    diagram_valg = st.radio(
        "Velg visning:",
        ["Kø", "Forsinkelser buss"],
        index=0
    )

    st.markdown("---")

    # Radio buttons for tid (Morgen / Ettermiddag)
    tid_valg = st.radio(
        "Tid på døgnet:",
        ["Morgen", "Ettermiddag"],
        index=0
    )

    st.markdown("---")

    # Dato-velger for startdato
    min_dato = df["dato"].min().date()
    max_dato = df["dato"].max().date()
    start_dato = st.date_input(
        "Startdato",
        value=min_dato,
        min_value=min_dato,
        max_value=max_dato
    )

# Filtrer på tid først
df_tid = df[df["tid"] == tid_valg]

# Filtrer på startdato
df_tid = df_tid[df_tid["dato"].dt.date >= start_dato]

# Lag dato-streng for x-aksen
df_tid = df_tid.copy()
df_tid["dato_str"] = df_tid["dato"].dt.strftime("%d.%m.%Y")

# Filtrer og aggreger data
if len(valgte_strekninger) == 0:
    # Ingen valgt = gjennomsnitt over alle strekninger
    df_filtered = df_tid.groupby(["dato", "dato_str"]).agg({
        "ko_min_km": "mean",
        "forsinkelser": "mean"
    }).reset_index()
    df_filtered["strekning"] = "Alle strekninger"
    tittel_suffix = f"alle strekninger ({tid_valg.lower()})"
else:
    # Filtrer på valgte strekninger
    df_filtered = df_tid[df_tid["stop_name"].isin(valgte_strekninger)].groupby(
        ["dato", "dato_str", "stop_name"]
    ).agg({
        "ko_min_km": "mean",
        "forsinkelser": "mean"
    }).reset_index()
    df_filtered = df_filtered.rename(columns={"stop_name": "strekning"})
    tittel_suffix = f"utvalgte strekninger ({tid_valg.lower()})"

# Sorter etter dato
df_filtered = df_filtered.sort_values("dato").reset_index(drop=True)

# Lag diagram basert på valg
if diagram_valg == "Kø":
    y_col = "ko_min_km"
    y_label = "Kø (min/km)"
    tittel = f"Kø - {tittel_suffix}"
else:
    y_col = "forsinkelser"
    y_label = "forsinkelser"
    tittel = f"Forsinkelser buss - {tittel_suffix}"

# Plotly linjediagram med dato som kategorisk x-akse
fig = px.line(
    df_filtered,
    x="dato_str",
    y=y_col,
    color="strekning",
    title=tittel,
    labels={"dato_str": "Dato", y_col: y_label, "strekning": "Strekning"}
)

fig.update_layout(
    xaxis_title="Dato",
    yaxis_title=y_label,
    hovermode="x unified",
    xaxis_tickangle=-45
)

# Vis diagram
st.plotly_chart(fig, use_container_width=True)

# Eksportmulighet
st.markdown("---")
col1, col2 = st.columns([1, 4])
with col1:
    # Forbered eksportdata
    export_df = df_filtered[["dato_str", "strekning", y_col]].rename(
        columns={"dato_str": "Dato", "strekning": "Strekning", y_col: y_label}
    )

    csv = export_df.to_csv(index=False, sep=";", decimal=",").encode("utf-8")
    st.download_button(
        label="📥 Eksporter CSV",
        data=csv,
        file_name=f"eksport_{diagram_valg.lower().replace(' ', '_')}.csv",
        mime="text/csv"
    )