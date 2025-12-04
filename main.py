import streamlit as st
import pandas as pd
import plotly.express as px

# Sidekonfigurasjon
st.set_page_config(page_title="Mobilitetsdashbord - Asker", layout="wide")

# Custom CSS for styling
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
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0px;
        background-color: #6b7b8c;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #6b7b8c;
        color: white;
        padding: 10px 30px;
        border-radius: 0;
    }
    .stTabs [aria-selected="true"] {
        background-color: #4a5a6a;
    }
</style>
""", unsafe_allow_html=True)


# ========== DATA LOADING ==========

@st.cache_data
def load_forsinkelser_data():
    """Last inn og preprosesser kødata"""
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


@st.cache_data
def load_reisestatistikk_data():
    """Last inn reisestatistikk-data (placeholder)"""
    # TODO: Implementer når CSV-fil er klar
    return None


# ========== PAGE: FORSINKELSER ==========

def page_forsinkelser():
    """Forsinkelser-siden"""

    # Last data
    try:
        df = load_forsinkelser_data()
    except FileNotFoundError:
        st.error("Kunne ikke finne datafil: data/inndata_asker_ko.csv")
        return

    # Sidebar
    with st.sidebar:
        st.markdown('<div class="sidebar-header">Velg gruppering</div>', unsafe_allow_html=True)

        # Multiselect for strekninger
        alle_strekninger = sorted(df["stop_name"].unique().tolist())
        valgte_strekninger = st.multiselect(
            "Strekning",
            options=alle_strekninger,
            default=[],
            placeholder="Alle strekninger",
            key="forsinkelser_strekninger"
        )

        st.markdown("---")

        # Radio buttons for valg av diagram (Kø / Forsinkelser)
        diagram_valg = st.radio(
            "Velg visning:",
            ["Kø", "Forsinkelser buss"],
            index=0,
            key="forsinkelser_diagram"
        )

        st.markdown("---")

        # Radio buttons for tid (Morgen / Ettermiddag)
        tid_valg = st.radio(
            "Tid på døgnet:",
            ["Morgen", "Ettermiddag"],
            index=0,
            key="forsinkelser_tid"
        )

        st.markdown("---")

        # Dato-velger for startdato
        min_dato = df["dato"].min().date()
        max_dato = df["dato"].max().date()
        start_dato = st.date_input(
            "Startdato",
            value=min_dato,
            min_value=min_dato,
            max_value=max_dato,
            key="forsinkelser_startdato"
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
        y_label = "Forsinkelser"
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
            mime="text/csv",
            key="forsinkelser_eksport"
        )


# ========== PAGE: REISESTATISTIKK ==========

def page_reisestatistikk():
    """Reisestatistikk-siden (placeholder)"""

    # Placeholder sidebar
    with st.sidebar:
        st.markdown('<div class="sidebar-header">Velg filtre</div>', unsafe_allow_html=True)
        st.write("*Filtre kommer når data er tilgjengelig*")

    st.header("Reisestatistikk")

    st.info("""
    🚧 **Denne siden er under utvikling**

    Her kommer reisestatistikk basert på data fra CSV-fil.

    Planlagte funksjoner:
    - Antall reiser per dag/uke/måned
    - Reisemønster fordelt på transportmiddel
    - Sammenligning mellom områder
    - Trendanalyse over tid
    """)


# ========== PAGE: FORSIDE ==========

def page_forside():
    """Forsiden med oversikt"""

    st.title("Mobilitetsdashbord for Asker")

    st.markdown("""
    Dette dashbordet gir en oversikt over sentrale mobilitetsindikatorer for Asker kommune. 
    Her kan du følge med på utviklingen i kø, forsinkelser og reisemønstre over tid.

    Dataene oppdateres jevnlig og gir grunnlag for å vurdere tiltak og effekter av 
    endringer i transportsystemet.
    """)

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📊 Forsinkelser")
        st.markdown("""
        Oversikt over kø og forsinkelser på utvalgte strekninger i Asker.

        - Køindeks (min/km) basert på trafikkdata
        - Forsinkelser for buss
        - Filtrer på tid (morgen/ettermiddag) og strekning
        """)

    with col2:
        st.subheader("🚌 Reisestatistikk")
        st.markdown("""
        Statistikk over reiser og reisemønstre.

        - *Kommer snart*
        """)


# ========== MAIN APP ==========

# Initialiser session state for navigasjon
if "current_page" not in st.session_state:
    st.session_state.current_page = "Hjem"

# Navigasjon øverst (stylet som tabs)
col1, col2, col3, col4 = st.columns([1, 1, 1, 3])
with col1:
    if st.button("Hjem", use_container_width=True,
                 type="primary" if st.session_state.current_page == "Hjem" else "secondary"):
        st.session_state.current_page = "Hjem"
        st.rerun()
with col2:
    if st.button("Forsinkelser", use_container_width=True,
                 type="primary" if st.session_state.current_page == "Forsinkelser" else "secondary"):
        st.session_state.current_page = "Forsinkelser"
        st.rerun()
with col3:
    if st.button("Reisestatistikk", use_container_width=True,
                 type="primary" if st.session_state.current_page == "Reisestatistikk" else "secondary"):
        st.session_state.current_page = "Reisestatistikk"
        st.rerun()

st.markdown("---")

# Vis riktig side basert på valg
if st.session_state.current_page == "Hjem":
    page_forside()
elif st.session_state.current_page == "Forsinkelser":
    page_forsinkelser()
else:
    page_reisestatistikk()