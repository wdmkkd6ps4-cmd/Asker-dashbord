import streamlit as st
import pandas as pd
import plotly.express as px
import clickhouse_connect

# === CLICKHOUSE EKSPORT (kjør separat for å oppdatere CSV) ===
client = clickhouse_connect.get_client(host='localhost', port=8123, database='asker')
df = client.query_df(
    "SELECT dato, klokkeslett, stop_name, tid_dag, faktisk_tid, avstand, min_tid, ko_min_km, forsinkelser, bil FROM `3-05 til dashbord ko`")
df.to_csv("data/inndata_asker_ko.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig")
print(f"Eksportert {len(df)} rader (kødata)")

# Eksport av reisestatistikk
df_reiser = client.query_df(
    "SELECT ID, kvartal, bil, buss, sykkel, gange, tog FROM `3-05 til dashbord reiser`")
df_reiser.to_csv("data/inndata_asker_reiser.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig")
print(f"Eksportert {len(df_reiser)} rader (reisestatistikk)")

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

    # Rensk kolonnenavn
    df.columns = df.columns.str.strip().str.replace('\ufeff', '')
    df.columns = df.columns.str.lower()

    # Konverter dato
    if df["dato"].dtype == 'object' and df["dato"].str.contains(",").any():
        df["dato"] = df["dato"].str.replace(",", ".")
        df["dato"] = pd.to_datetime(df["dato"], format="%d.%m.%Y")
    else:
        df["dato"] = pd.to_datetime(df["dato"])

    # Konverter klokkeslett til streng (HH:MM)
    if "klokkeslett" in df.columns:
        df["klokkeslett"] = pd.to_datetime(df["klokkeslett"].astype(str)).dt.strftime("%H:%M")

    # Håndter tomme verdier
    df["forsinkelser"] = pd.to_numeric(df["forsinkelser"], errors="coerce")
    df["ko_min_km"] = pd.to_numeric(df["ko_min_km"], errors="coerce")
    if "bil" in df.columns:
        df["bil"] = pd.to_numeric(df["bil"], errors="coerce")

    return df


@st.cache_data
def load_reisestatistikk_data():
    """Last inn og preprosesser reisestatistikk-data"""
    df = pd.read_csv(
        "data/inndata_asker_reiser.csv",
        sep=";",
        decimal=",",
        encoding="utf-8-sig"
    )

    # Rensk kolonnenavn
    df.columns = df.columns.str.strip().str.replace('\ufeff', '')

    # Konverter numeriske kolonner
    for col in ["bil", "buss", "sykkel", "gange", "tog"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Lag sorteringsnøkkel for kvartal (YYYY-Q -> YYYYQ for sortering)
    df["kvartal_sort"] = df["kvartal"].str.replace("-", "").astype(int)

    # Sorter kronologisk
    df = df.sort_values("kvartal_sort").reset_index(drop=True)

    return df


# ========== PAGE: FORSINKELSER ==========

def page_forsinkelser():
    """Forsinkelser-siden"""

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

        # Radio buttons for visning (Kø / Forsinkelser)
        diagram_valg = st.radio(
            "Velg visning:",
            ["Kø", "Forsinkelser buss"],
            index=0,
            key="forsinkelser_diagram"
        )

        st.markdown("---")

        # Radio buttons for x-akse (Over dato / Over klokkeslett)
        x_akse_valg = st.radio(
            "Vis over:",
            ["Over dato", "Over klokkeslett"],
            index=0,
            key="forsinkelser_x_akse"
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

        # Dato-velger for startdato (kun relevant for "Over dato")
        min_dato = df["dato"].min().date()
        max_dato = df["dato"].max().date()
        start_dato = st.date_input(
            "Startdato",
            value=min_dato,
            min_value=min_dato,
            max_value=max_dato,
            key="forsinkelser_startdato",
            disabled=(x_akse_valg == "Over klokkeslett")
        )

    # Filtrer på tid
    df_tid = df[df["tid_dag"] == tid_valg].copy()

    # Filtrer på startdato (kun for "Over dato")
    if x_akse_valg == "Over dato":
        df_tid = df_tid[df_tid["dato"].dt.date >= start_dato]

    # Velg y-kolonne
    if diagram_valg == "Kø":
        y_col = "ko_min_km"
        y_label = "Kø (min/km)"
    else:
        y_col = "forsinkelser"
        y_label = "Forsinkelser (min)"

    # Filtrer bort rader uten verdi i y-kolonnen
    df_tid = df_tid[df_tid[y_col].notna()]

    if len(df_tid) == 0:
        st.warning("Ingen data tilgjengelig for valgte filtre.")
        return

    # ===== OVER DATO =====
    if x_akse_valg == "Over dato":
        df_tid["dato_str"] = df_tid["dato"].dt.strftime("%d.%m.%Y")

        if len(valgte_strekninger) == 0:
            # Vektet gjennomsnitt over alle strekninger og klokkeslett per dato
            def weighted_avg(group):
                mask = group[y_col].notna() & group["bil"].notna()
                if mask.sum() == 0:
                    return pd.NA
                return (group.loc[mask, y_col] * group.loc[mask, "bil"]).sum() / group.loc[mask, "bil"].sum()

            df_plot = df_tid.groupby(["dato", "dato_str"]).apply(weighted_avg).reset_index(name=y_col)
            df_plot["strekning"] = "Alle strekninger"
            tittel_suffix = f"alle strekninger ({tid_valg.lower()})"
        else:
            # Median over klokkeslett per dato og strekning
            df_plot = df_tid[df_tid["stop_name"].isin(valgte_strekninger)].groupby(
                ["dato", "dato_str", "stop_name"]
            ).agg({
                y_col: "median"
            }).reset_index()
            df_plot = df_plot.rename(columns={"stop_name": "strekning"})
            tittel_suffix = f"utvalgte strekninger ({tid_valg.lower()})"

        df_plot = df_plot.sort_values("dato").reset_index(drop=True)
        tittel = f"{diagram_valg} - {tittel_suffix}"

        fig = px.line(
            df_plot,
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
            xaxis_tickangle=-45,
            yaxis_rangemode="tozero"
        )

    # ===== OVER KLOKKESLETT =====
    else:
        if len(valgte_strekninger) == 0:
            # Vektet gjennomsnitt over alle strekninger og datoer per klokkeslett
            def weighted_avg(group):
                mask = group[y_col].notna() & group["bil"].notna()
                if mask.sum() == 0:
                    return pd.NA
                return (group.loc[mask, y_col] * group.loc[mask, "bil"]).sum() / group.loc[mask, "bil"].sum()

            df_plot = df_tid.groupby("klokkeslett").apply(weighted_avg).reset_index(name=y_col)
            df_plot["strekning"] = "Alle strekninger"
            tittel_suffix = f"alle strekninger ({tid_valg.lower()})"
        else:
            # Median over datoer per klokkeslett og strekning
            df_plot = df_tid[df_tid["stop_name"].isin(valgte_strekninger)].groupby(
                ["klokkeslett", "stop_name"]
            ).agg({
                y_col: "median"
            }).reset_index()
            df_plot = df_plot.rename(columns={"stop_name": "strekning"})
            tittel_suffix = f"utvalgte strekninger ({tid_valg.lower()})"

        # Sorter klokkeslett
        df_plot = df_plot.sort_values("klokkeslett").reset_index(drop=True)
        tittel = f"{diagram_valg} - {tittel_suffix}"

        fig = px.bar(
            df_plot,
            x="klokkeslett",
            y=y_col,
            color="strekning",
            barmode="group",
            title=tittel,
            labels={"klokkeslett": "Klokkeslett", y_col: y_label, "strekning": "Strekning"}
        )
        fig.update_layout(
            xaxis_title="Klokkeslett",
            yaxis_title=y_label,
            hovermode="x unified",
            yaxis_rangemode="tozero"
        )

    # Vis diagram
    st.plotly_chart(fig, use_container_width=True)

    # Eksportmulighet
    st.markdown("---")
    col1, col2 = st.columns([1, 4])
    with col1:
        if x_akse_valg == "Over dato":
            export_df = df_plot[["dato_str", "strekning", y_col]].rename(
                columns={"dato_str": "Dato", "strekning": "Strekning", y_col: y_label}
            )
        else:
            export_df = df_plot[["klokkeslett", "strekning", y_col]].rename(
                columns={"klokkeslett": "Klokkeslett", "strekning": "Strekning", y_col: y_label}
            )

        csv = export_df.to_csv(index=False, sep=";", decimal=",").encode("utf-8")
        st.download_button(
            label="📥 Eksporter CSV",
            data=csv,
            file_name=f"eksport_{diagram_valg.lower().replace(' ', '_')}.csv",
            mime="text/csv",
            key="forsinkelser_eksport"
        )


# ========== PAGE: KART ==========

def page_kart():
    """Kartside med QGIS Cloud-kart"""

    st.header("Kart - Asker sentrum")

    qgis_url = "https://qgiscloud.com/jaleas/Asker_sentrum_cloud/?l=Til%20Asker%20sentrum%20Morgen%2CFra%20Asker%20sentrum%20Ettermiddag!%2CGjennomfart%20Asker%20Syd-Nord%20uE18!%2CGjennomfart%20Asker%20Syd-Nord%20!%2CGjennomfart%20Asker%20Syd-Vest%20!%2CGjennomfart%20Asker%20Syd-Vest%20uE18!%2Cshapefile_nor_grids_norway_grids!%2CAsker%20sentrum%5B43%5D%2CSoner%20Syd%20Vest%20og%20Nord%5B78%5D!%2CGrey&t=Asker_sentrum_cloud&e=1083531%2C8299266%2C1245033%2C8422138"

    st.markdown("Interaktivt kart som viser trafikkmønstre i Asker sentrum.")

    # Vis kartbilde som klikkbar thumbnail (mindre størrelse)
    try:
        import base64
        with open("data/kart_thumbnail.png", "rb") as f:
            img_data = base64.b64encode(f.read()).decode()

        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            st.markdown(
                f'<a href="{qgis_url}" target="_blank">'
                f'<img src="data:image/png;base64,{img_data}" style="width:100%; border:2px solid #2c5f7c; border-radius:8px; cursor:pointer;">'
                f'</a>',
                unsafe_allow_html=True
            )
    except:
        st.info("Kartforhåndsvisning ikke tilgjengelig")

    st.link_button("🗺️ Åpne interaktivt kart i ny fane", qgis_url, use_container_width=True)

    st.markdown("---")
    st.markdown("""
    **Tilgjengelige lag i kartet:**
    - Til Asker sentrum (Morgen)
    - Fra Asker sentrum (Ettermiddag)
    - Gjennomfartstrafikk Syd-Nord
    - Gjennomfartstrafikk Syd-Vest
    - Soner og grids
    """)


# ========== PAGE: REISESTATISTIKK ==========

def page_reisestatistikk():
    """Reisestatistikk-siden med linjediagram over kvartal"""

    try:
        df = load_reisestatistikk_data()
    except FileNotFoundError:
        st.error("Kunne ikke finne datafil: data/inndata_asker_reiser.csv")
        return

    # Hent unike ID-verdier dynamisk fra dataene
    alle_id = sorted(df["ID"].unique().tolist())

    # Finn default-indeks for "Til Asker sentrum"
    default_id = "Til Asker sentrum"
    if default_id in alle_id:
        default_index = alle_id.index(default_id)
    else:
        default_index = 0

    # Sidebar
    with st.sidebar:
        st.markdown('<div class="sidebar-header">Velg strekning</div>', unsafe_allow_html=True)

        valgt_id = st.selectbox(
            "Strekning",
            options=alle_id,
            index=default_index,
            key="reisestatistikk_id"
        )

    # Filtrer data på valgt ID
    df_filtered = df[df["ID"] == valgt_id].copy()

    if len(df_filtered) == 0:
        st.warning("Ingen data tilgjengelig for valgt strekning.")
        return

    # Forbered data for plotting - smelt til lang format
    transportmidler = ["bil", "buss", "sykkel", "gange", "tog"]
    df_plot = df_filtered.melt(
        id_vars=["kvartal", "kvartal_sort"],
        value_vars=transportmidler,
        var_name="Transportmiddel",
        value_name="Antall reiser"
    )

    # Sorter etter kvartal
    df_plot = df_plot.sort_values("kvartal_sort").reset_index(drop=True)

    # Lag penere navn på transportmidler (stor forbokstav)
    df_plot["Transportmiddel"] = df_plot["Transportmiddel"].str.capitalize()

    # Definer farger for transportmidler
    farger = {
        "Bil": "#636EFA",
        "Buss": "#EF553B",
        "Sykkel": "#00CC96",
        "Gange": "#AB63FA",
        "Tog": "#FFA15A"
    }

    # Lag linjediagram
    fig = px.line(
        df_plot,
        x="kvartal",
        y="Antall reiser",
        color="Transportmiddel",
        title=f"Reisestatistikk - {valgt_id} (1000 reiser per kvartal)",
        labels={"kvartal": "Kvartal", "Antall reiser": "Antall reiser (1000 per kvartal)"},
        color_discrete_map=farger
    )

    fig.update_layout(
        xaxis_title="Kvartal",
        yaxis_title="Antall reiser (1000 per kvartal)",
        hovermode="x unified",
        xaxis_tickangle=-45,
        yaxis_rangemode="tozero",
        legend_title="Transportmiddel",
        xaxis_type="category"
    )

    # Vis diagram
    st.plotly_chart(fig, use_container_width=True)

    # Eksportmulighet
    st.markdown("---")
    col1, col2 = st.columns([1, 4])
    with col1:
        export_df = df_filtered[["kvartal"] + transportmidler].rename(
            columns={
                "kvartal": "Kvartal",
                "bil": "Bil",
                "buss": "Buss",
                "sykkel": "Sykkel",
                "gange": "Gange",
                "tog": "Tog"
            }
        )
        csv = export_df.to_csv(index=False, sep=";", decimal=",").encode("utf-8")
        st.download_button(
            label="📥 Eksporter CSV",
            data=csv,
            file_name=f"eksport_reisestatistikk_{valgt_id.lower().replace(' ', '_')}.csv",
            mime="text/csv",
            key="reisestatistikk_eksport"
        )


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

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("📊 Forsinkelser")
        st.markdown("""
        Oversikt over kø og forsinkelser på utvalgte strekninger i Asker.

        - Køindeks (min/km) basert på trafikkdata
        - Forsinkelser for buss
        - Filtrer på tid (morgen/ettermiddag) og strekning
        - Vis over dato eller klokkeslett
        """)

    with col2:
        st.subheader("🗺️ Kart")
        st.markdown("""
        Interaktivt kart over Asker sentrum.

        - Trafikkmønstre til/fra sentrum
        - Gjennomfartstrafikk
        - Soner og grids
        """)

    with col3:
        st.subheader("🚌 Reisestatistikk")
        st.markdown("""
        Statistikk over reiser og reisemønstre.

        - Antall reiser per kvartal
        - Fordelt på transportmiddel
        - Filtrer på strekning
        """)


# ========== MAIN APP ==========

if "current_page" not in st.session_state:
    st.session_state.current_page = "Hjem"

col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 2])
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
with col4:
    if st.button("Kart", use_container_width=True,
                 type="primary" if st.session_state.current_page == "Kart" else "secondary"):
        st.session_state.current_page = "Kart"
        st.rerun()

st.markdown("---")

if st.session_state.current_page == "Hjem":
    page_forside()
elif st.session_state.current_page == "Forsinkelser":
    page_forsinkelser()
elif st.session_state.current_page == "Kart":
    page_kart()
else:
    page_reisestatistikk()