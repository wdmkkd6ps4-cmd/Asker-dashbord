"""
generer_dashboard.py

Genererer en statisk HTML-fil med interaktive Plotly-grafer og JavaScript-filtre.
HTML-filen kan hostes på GitHub Pages.

Bruk:
    python generer_dashboard.py

Output:
    docs/index.html (legg denne i docs/ for GitHub Pages)
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime


def load_and_process_ko_data(filepath):
    """Last inn og preprosesser kødata"""
    df = pd.read_csv(filepath, sep=";", decimal=",", encoding="utf-8-sig")
    df.columns = df.columns.str.strip().str.replace('\ufeff', '')
    df.columns = df.columns.str.lower()

    df["dato"] = pd.to_datetime(df["dato"])
    df["dato_str"] = df["dato"].dt.strftime("%d.%m.%Y")

    df["forsinkelser"] = pd.to_numeric(df["forsinkelser"], errors="coerce")
    df["ko_min_km"] = pd.to_numeric(df["ko_min_km"], errors="coerce")
    df["bil"] = pd.to_numeric(df["bil"], errors="coerce")

    return df


def load_and_process_reiser_data(filepath):
    """Last inn og preprosesser reisedata"""
    df = pd.read_csv(filepath, sep=";", decimal=",", encoding="utf-8-sig")
    df.columns = df.columns.str.strip().str.replace('\ufeff', '')

    for col in ["bil", "buss", "sykkel", "gange", "tog"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["kvartal_sort"] = df["kvartal"].str.replace("-", "").astype(int)
    df = df.sort_values("kvartal_sort").reset_index(drop=True)

    return df


def load_and_process_nokkel_data(filepath):
    """Last inn og preprosesser nøkkeltalldata"""
    df = pd.read_csv(filepath, sep=";", decimal=",", encoding="utf-8-sig")
    df.columns = df.columns.str.strip().str.replace('\ufeff', '')

    # Behandle delområder som string
    df["delomrade_fra"] = df["delomrade_fra"].astype(str).str.strip()
    df["delomrade_til"] = df["delomrade_til"].astype(str).str.strip()

    df["reiser"] = pd.to_numeric(df["reiser"], errors="coerce")

    # Lag sorteringsnøkkel for kvartal
    df["kvartal_sort"] = df["kvartal"].str.replace("-", "").astype(int)

    return df


def aggregate_ko_data(df):
    """Aggreger kødata for grafer"""
    aggregated = {}

    for tid_dag in ["Morgen", "Ettermiddag"]:
        df_tid = df[df["tid_dag"] == tid_dag].copy()

        if len(df_tid) == 0:
            continue

        def weighted_avg_ko(group):
            mask = group["ko_min_km"].notna() & group["bil"].notna() & (group["bil"] > 0)
            if mask.sum() == 0:
                return np.nan
            return (group.loc[mask, "ko_min_km"] * group.loc[mask, "bil"]).sum() / group.loc[mask, "bil"].sum()

        def weighted_avg_forsinkelser(group):
            mask = group["forsinkelser"].notna() & group["bil"].notna() & (group["bil"] > 0)
            if mask.sum() == 0:
                return np.nan
            return (group.loc[mask, "forsinkelser"] * group.loc[mask, "bil"]).sum() / group.loc[mask, "bil"].sum()

        agg_alle_dato = df_tid.groupby("dato").apply(
            lambda g: pd.Series({
                "ko_min_km": weighted_avg_ko(g),
                "forsinkelser": weighted_avg_forsinkelser(g)
            }), include_groups=False
        ).reset_index()
        agg_alle_dato = agg_alle_dato.sort_values("dato")
        agg_alle_dato["dato_str"] = agg_alle_dato["dato"].dt.strftime("%d.%m.%Y")

        key = f"Alle strekninger_{tid_dag}"
        aggregated[key] = {
            "datoer": agg_alle_dato["dato_str"].tolist(),
            "ko": [round(x, 3) if pd.notna(x) else None for x in agg_alle_dato["ko_min_km"].tolist()],
            "forsinkelser": [round(x, 3) if pd.notna(x) else None for x in agg_alle_dato["forsinkelser"].tolist()]
        }

        agg_alle_klokke = df_tid.groupby("klokkeslett").apply(
            lambda g: pd.Series({
                "ko_min_km": weighted_avg_ko(g),
                "forsinkelser": weighted_avg_forsinkelser(g)
            }), include_groups=False
        ).reset_index()
        agg_alle_klokke = agg_alle_klokke.sort_values("klokkeslett")

        key = f"Alle strekninger_{tid_dag}_klokkeslett"
        aggregated[key] = {
            "klokkeslett": agg_alle_klokke["klokkeslett"].tolist(),
            "ko": [round(x, 3) if pd.notna(x) else None for x in agg_alle_klokke["ko_min_km"].tolist()],
            "forsinkelser": [round(x, 3) if pd.notna(x) else None for x in agg_alle_klokke["forsinkelser"].tolist()]
        }

        for stop in df_tid["stop_name"].dropna().unique():
            df_stop = df_tid[df_tid["stop_name"] == stop]

            agg = df_stop.groupby(["dato", "dato_str"]).agg({
                "ko_min_km": "median",
                "forsinkelser": "median"
            }).reset_index()
            agg = agg.sort_values("dato")

            key = f"{stop}_{tid_dag}"
            aggregated[key] = {
                "datoer": agg["dato_str"].tolist(),
                "ko": [round(x, 3) if pd.notna(x) else None for x in agg["ko_min_km"].tolist()],
                "forsinkelser": [round(x, 3) if pd.notna(x) else None for x in agg["forsinkelser"].tolist()]
            }

            agg_klokke = df_stop.groupby("klokkeslett").agg({
                "ko_min_km": "median",
                "forsinkelser": "median"
            }).reset_index()
            agg_klokke = agg_klokke.sort_values("klokkeslett")

            key = f"{stop}_{tid_dag}_klokkeslett"
            aggregated[key] = {
                "klokkeslett": agg_klokke["klokkeslett"].tolist(),
                "ko": [round(x, 3) if pd.notna(x) else None for x in agg_klokke["ko_min_km"].tolist()],
                "forsinkelser": [round(x, 3) if pd.notna(x) else None for x in agg_klokke["forsinkelser"].tolist()]
            }

    return aggregated


def prepare_nokkel_data(df):
    """Forbered nøkkeltalldata for JavaScript"""
    # Lag liste over unike verdier
    omrader_fra = sorted(df["delomrade_fra"].unique().tolist())
    omrader_til = sorted(df["delomrade_til"].unique().tolist())
    tider = sorted(df["time_of_day"].unique().tolist())
    kvartaler = df.sort_values("kvartal_sort")["kvartal"].unique().tolist()

    # Konverter hele datasettet til liste av dicts for JavaScript (uten trend - beregnes i JS)
    records = df[
        ["delomrade_fra", "delomrade_til", "kvartal", "reiser", "time_of_day", "weekday_indicator"]].to_dict(
        "records")

    return {
        "records": records,
        "omrader_fra": omrader_fra,
        "omrader_til": omrader_til,
        "tider": tider,
        "kvartaler": kvartaler
    }


def generate_html(ko_data, reiser_data, ko_aggregated, nokkel_data):
    """Generer HTML med embedded data og JavaScript"""

    strekninger_ko = ["Alle strekninger"] + sorted(ko_data["stop_name"].dropna().unique().tolist())
    strekninger_reiser = sorted(reiser_data["ID"].unique().tolist())

    # Forbered reisedata som dict
    reiser_dict = {}
    for strekning in strekninger_reiser:
        df_s = reiser_data[reiser_data["ID"] == strekning].sort_values("kvartal_sort")
        reiser_dict[strekning] = {
            "kvartaler": df_s["kvartal"].tolist(),
            "bil": [round(x, 2) if pd.notna(x) else None for x in df_s["bil"].tolist()],
            "buss": [round(x, 2) if pd.notna(x) else None for x in df_s["buss"].tolist()],
            "sykkel": [round(x, 2) if pd.notna(x) else None for x in df_s["sykkel"].tolist()],
            "gange": [round(x, 2) if pd.notna(x) else None for x in df_s["gange"].tolist()],
            "tog": [round(x, 2) if pd.notna(x) else None for x in df_s["tog"].tolist()]
        }

    # Generer options for flervalg
    omrade_fra_options = '<option value="Alle" selected>Alle</option>\n' + \
                         "\n".join(f'<option value="{o}">{o}</option>' for o in nokkel_data["omrader_fra"])
    omrade_til_options = '<option value="Alle" selected>Alle</option>\n' + \
                         "\n".join(f'<option value="{o}">{o}</option>' for o in nokkel_data["omrader_til"])

    # Generer radiobuttons for tid på dagen
    tid_radios = '<label><input type="radio" name="tid-nokkel" value="Alle" checked onchange="updateNokkelChart()"> Alle</label>\n'
    for tid in sorted(nokkel_data["tider"]):
        tid_radios += f'<label><input type="radio" name="tid-nokkel" value="{tid}" onchange="updateNokkelChart()"> {tid}</label>\n'

    html = f'''<!DOCTYPE html>
<html lang="no">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mobilitetsdashbord - Asker</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #f5f5f5;
        }}
        .header {{
            background-color: #2c5f7c;
            color: white;
            padding: 20px;
            text-align: center;
        }}
        .nav {{
            display: flex;
            gap: 0;
            background-color: #6b7b8c;
            padding: 0;
        }}
        .nav button {{
            background-color: #6b7b8c;
            color: white;
            border: none;
            padding: 15px 30px;
            cursor: pointer;
            font-size: 16px;
            transition: background-color 0.2s;
        }}
        .nav button:hover {{
            background-color: #5a6a7a;
        }}
        .nav button.active {{
            background-color: #4a5a6a;
        }}
        .container {{
            display: flex;
            min-height: calc(100vh - 120px);
        }}
        .sidebar {{
            width: 280px;
            background-color: #e8e8e8;
            padding: 20px;
            flex-shrink: 0;
        }}
        .sidebar h3 {{
            background-color: #2c5f7c;
            color: white;
            padding: 15px;
            margin: -20px -20px 20px -20px;
        }}
        .sidebar label {{
            display: block;
            margin-top: 15px;
            font-weight: bold;
        }}
        .sidebar select, .sidebar input {{
            width: 100%;
            padding: 8px;
            margin-top: 5px;
            border: 1px solid #ccc;
            border-radius: 4px;
        }}
        .sidebar select[multiple] {{
            height: 150px;
        }}
        .sidebar hr {{
            margin: 20px 0;
            border: none;
            border-top: 1px solid #ccc;
        }}
        .main {{
            flex: 1;
            padding: 30px;
        }}
        .page {{
            display: none;
        }}
        .page.active {{
            display: block;
        }}
        .chart {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .sankey-btn {{
            background-color: #2c5f7c;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-top: 10px;
        }}
        .sankey-btn:hover {{
            background-color: #1e4a5f;
        }}
        .chart-buttons {{
            display: flex;
            gap: 10px;
            margin-top: 10px;
        }}
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
        }}
        .modal-content {{
            background-color: white;
            margin: 2% auto;
            padding: 20px;
            border-radius: 8px;
            width: 95%;
            max-width: 1100px;
            max-height: 90vh;
            overflow-y: auto;
        }}
        .modal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
        }}
        .modal-header h2 {{
            margin: 0;
            color: #2c5f7c;
        }}
        .modal-close {{
            font-size: 28px;
            cursor: pointer;
            color: #666;
        }}
        .modal-close:hover {{
            color: #333;
        }}
        .sankey-controls {{
            display: flex;
            gap: 20px;
            margin-bottom: 15px;
            align-items: center;
        }}
        .sankey-controls label {{
            display: flex;
            align-items: center;
            gap: 5px;
            cursor: pointer;
        }}
        .sankey-controls label.disabled {{
            display: none;
        }}
        .home-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
        }}
        .home-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .home-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        .home-card h3 {{
            margin-bottom: 15px;
            color: #2c5f7c;
        }}
        .kart-thumbnail {{
            width: 300px;
            border: 2px solid #2c5f7c;
            border-radius: 8px;
            cursor: pointer;
            transition: transform 0.2s;
        }}
        .kart-thumbnail:hover {{
            transform: scale(1.02);
        }}
        .kart-button {{
            display: inline-block;
            background-color: #2c5f7c;
            color: white;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 4px;
            margin-top: 15px;
        }}
        .kart-button:hover {{
            background-color: #1e4a5f;
        }}
        .radio-group {{
            margin-top: 10px;
        }}
        .radio-group label {{
            display: flex;
            align-items: center;
            font-weight: normal;
            margin-top: 8px;
            cursor: pointer;
        }}
        .radio-group input {{
            width: auto;
            margin-right: 8px;
        }}
        .filter-hint {{
            font-size: 12px;
            color: #666;
            margin-top: 5px;
            font-weight: normal;
        }}
        @media (max-width: 900px) {{
            .container {{
                flex-direction: column;
            }}
            .sidebar {{
                width: 100%;
            }}
            .home-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Mobilitetsdashbord for Asker</h1>
    </div>

    <div class="nav">
        <button class="active" onclick="showPage('hjem')">Hjem</button>
        <button onclick="showPage('forsinkelser')">Forsinkelser og køer</button>
        <button onclick="showPage('reisestatistikk')">Reisestatistikk Asker sentrum</button>
        <button onclick="showPage('nokkeltall')">Reisestrømmer i Asker kommune</button>
        <button onclick="showPage('kart')">Kart</button>
    </div>

    <div class="container">
        <div class="sidebar" id="sidebar-forsinkelser" style="display: none;">
            <h3>Velg filtre</h3>

            <label for="strekning-ko">Strekning</label>
            <select id="strekning-ko" onchange="updateKoChart()">
                {"".join(f'<option value="{s}"' + (' selected' if s == 'Alle strekninger' else '') + f'>{s}</option>' for s in strekninger_ko)}
            </select>

            <hr>

            <label>Velg visning:</label>
            <div class="radio-group">
                <label><input type="radio" name="visning" value="ko" checked onchange="updateKoChart()"> Kø</label>
                <label><input type="radio" name="visning" value="forsinkelser" onchange="updateKoChart()"> Forsinkelser buss</label>
            </div>

            <hr>

            <label>Vis over:</label>
            <div class="radio-group">
                <label><input type="radio" name="xakse" value="dato" checked onchange="updateKoChart()"> Over dato</label>
                <label><input type="radio" name="xakse" value="klokkeslett" onchange="updateKoChart()"> Over klokkeslett</label>
            </div>

            <hr>

            <label>Tid på døgnet:</label>
            <div class="radio-group">
                <label><input type="radio" name="tid" value="Morgen" checked onchange="updateKoChart()"> Morgen</label>
                <label><input type="radio" name="tid" value="Ettermiddag" onchange="updateKoChart()"> Ettermiddag</label>
            </div>
        </div>

        <div class="sidebar" id="sidebar-reisestatistikk" style="display: none;">
            <h3>Velg strekning</h3>

            <label for="strekning-reiser">Strekning</label>
            <select id="strekning-reiser" onchange="updateReiserChart()">
                {"".join(f'<option value="{s}"' + (' selected' if s == 'Til Asker sentrum' else '') + f'>{s}</option>' for s in strekninger_reiser)}
            </select>
        </div>

        <div class="sidebar" id="sidebar-nokkeltall" style="display: none;">
            <h3>Velg filtre</h3>

            <label for="omrade-fra">Område fra</label>
            <select id="omrade-fra" multiple onchange="updateNokkelChart()">
                {omrade_fra_options}
            </select>
            <div class="filter-hint">Ctrl+klikk for flervalg</div>

            <label for="omrade-til">Område til</label>
            <select id="omrade-til" multiple onchange="updateNokkelChart()">
                {omrade_til_options}
            </select>
            <div class="filter-hint">Ctrl+klikk for flervalg</div>

            <hr>

            <label>Tid på dagen:</label>
            <div class="radio-group">
                {tid_radios}
            </div>

            <hr>

            <label>Ukedag/helg:</label>
            <div class="radio-group">
                <label><input type="radio" name="ukedag-nokkel" value="Alle" checked onchange="updateNokkelChart()"> Alle</label>
                <label><input type="radio" name="ukedag-nokkel" value="Weekday" onchange="updateNokkelChart()"> Ukedag</label>
                <label><input type="radio" name="ukedag-nokkel" value="Weekend" onchange="updateNokkelChart()"> Helg</label>
            </div>
        </div>

        <div class="main">
            <!-- HJEM -->
            <div class="page active" id="page-hjem">
                <h2>Velkommen til Mobilitetsdashbordet</h2>
                <p style="margin: 20px 0;">
                    Dette dashbordet gir en oversikt over sentrale mobilitetsindikatorer for Asker kommune.
                    Her kan du følge med på utviklingen i kø, forsinkelser og reisemønstre over tid.
                </p>

                <div class="home-grid">
                    <div class="home-card" onclick="navigateTo('forsinkelser')">
                        <h3>📊 Forsinkelser og køer</h3>
                        <p>Oversikt over kø og forsinkelser på utvalgte strekninger i Asker.</p>
                        <ul style="margin-top: 10px; margin-left: 20px;">
                            <li>Køindeks (min/km)</li>
                            <li>Forsinkelser for buss</li>
                            <li>Filtrer på tid og strekning</li>
                        </ul>
                    </div>
                    <div class="home-card" onclick="navigateTo('kart')">
                        <h3>🗺️ Kart</h3>
                        <p>Interaktivt kart over Asker sentrum.</p>
                        <ul style="margin-top: 10px; margin-left: 20px;">
                            <li>Trafikkmønstre til/fra sentrum</li>
                            <li>Gjennomfartstrafikk</li>
                            <li>Oversikt over køer</li>
                            <li>Soner og grids</li>
                        </ul>
                    </div>
                    <div class="home-card" onclick="navigateTo('reisestatistikk')">
                        <h3>🚌 Reisestatistikk Asker sentrum</h3>
                        <p>Statistikk over reiser og reisemønstre.</p>
                        <ul style="margin-top: 10px; margin-left: 20px;">
                            <li>Antall reiser per kvartal</li>
                            <li>Fordelt på transportmiddel</li>
                            <li>Filtrer på strekning</li>
                        </ul>
                    </div>
                    <div class="home-card" onclick="navigateTo('nokkeltall')">
                        <h3>📈 Reisestrømmer i Asker kommune</h3>
                        <p>Detaljert reisestatistikk mellom områder.</p>
                        <ul style="margin-top: 10px; margin-left: 20px;">
                            <li>Filtrer på fra/til-område</li>
                            <li>Tid på dagen</li>
                            <li>Ukedag/helg</li>
                        </ul>
                    </div>
                </div>
            </div>

            <!-- FORSINKELSER -->
            <div class="page" id="page-forsinkelser">
                <div class="chart">
                    <div id="ko-chart" style="height: 500px;"></div>
                </div>
            </div>

            <!-- REISESTATISTIKK -->
            <div class="page" id="page-reisestatistikk">
                <div class="chart">
                    <div id="reiser-chart" style="height: 500px;"></div>
                </div>
            </div>

            <!-- NØKKELTALL REISER -->
            <div class="page" id="page-nokkeltall">
                <div class="chart">
                    <div id="nokkel-chart" style="height: 500px;"></div>
                    <div class="chart-buttons">
                        <button id="sankey-btn" class="sankey-btn" onclick="openSankeyModal()" style="display: none;">📊 Vis reisestrømmer</button>
                        <button id="csv-btn" class="sankey-btn" onclick="exportCSV()">📥 Eksporter CSV</button>
                    </div>
                </div>
            </div>

            <!-- SANKEY MODAL -->
            <div id="sankey-modal" class="modal">
                <div class="modal-content">
                    <div class="modal-header">
                        <h2>Reisestrømmer</h2>
                        <span class="modal-close" onclick="closeSankeyModal()">&times;</span>
                    </div>
                    <div class="sankey-controls" id="sankey-controls">
                        <span><strong>Vis retning:</strong></span>
                        <label id="sankey-fra-label"><input type="radio" name="sankey-retning" value="fra" checked onchange="updateSankeyChart()"> Fra valgte områder</label>
                        <label id="sankey-til-label"><input type="radio" name="sankey-retning" value="til" onchange="updateSankeyChart()"> Til valgte områder</label>
                    </div>
                    <div id="sankey-chart" style="height: 600px;"></div>
                    <p style="color: #666; font-size: 12px; margin-top: 10px;">Viser topp 10 relasjoner basert på siste 4 kvartaler.</p>
                </div>
            </div>

            <!-- KART -->
            <div class="page" id="page-kart">
                <h2>Kart - Asker sentrum</h2>
                <p style="margin: 20px 0;">Interaktivt kart som viser trafikkmønstre i Asker sentrum.</p>

                <a href="https://qgiscloud.com/jaleas/Asker_sentrum_cloud/?l=Til%20Asker%20sentrum%20Morgen%2CFra%20Asker%20sentrum%20Ettermiddag!%2CGjennomfart%20Asker%20Syd-Nord%20uE18!%2CGjennomfart%20Asker%20Syd-Nord%20!%2CGjennomfart%20Asker%20Syd-Vest%20!%2CGjennomfart%20Asker%20Syd-Vest%20uE18!%2CKart%20over%20koer!%2CAsker%20sentrum%5B43%5D%2CSoner%20Syd%20Vest%20og%20Nord%5B78%5D!%2CGrey&t=Asker_sentrum_cloud&e=1148232%2C8344108%2C1180532%2C8368683" target="_blank">
                    <img src="https://raw.githubusercontent.com/wdmkkd6ps4-cmd/Asker-dashbord/main/data/kart_thumbnail.png" class="kart-thumbnail" alt="Kart over Asker">
                </a>

                <br>

                <a href="https://qgiscloud.com/jaleas/Asker_sentrum_cloud/?l=Til%20Asker%20sentrum%20Morgen%2CFra%20Asker%20sentrum%20Ettermiddag!%2CGjennomfart%20Asker%20Syd-Nord%20uE18!%2CGjennomfart%20Asker%20Syd-Nord%20!%2CGjennomfart%20Asker%20Syd-Vest%20!%2CGjennomfart%20Asker%20Syd-Vest%20uE18!%2CKart%20over%20koer!%2CAsker%20sentrum%5B43%5D%2CSoner%20Syd%20Vest%20og%20Nord%5B78%5D!%2CGrey&t=Asker_sentrum_cloud&e=1148232%2C8344108%2C1180532%2C8368683" target="_blank" class="kart-button">
                    🗺️ Åpne interaktivt kart i ny fane
                </a>

                <div style="margin-top: 30px;">
                    <h3>Tilgjengelige lag i kartet:</h3>
                    <ul style="margin-top: 10px; margin-left: 20px;">
                        <li>Til Asker sentrum (Morgen)</li>
                        <li>Fra Asker sentrum (Ettermiddag)</li>
                        <li>Gjennomfartstrafikk Syd-Nord</li>
                        <li>Gjennomfartstrafikk Syd-Vest</li>
                        <li>Oversiktskart over køer</li>
                        <li>Soner og grids</li>
                    </ul>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Embedded data
        const koData = {json.dumps(ko_aggregated, ensure_ascii=False)};
        const reiserData = {json.dumps(reiser_dict, ensure_ascii=False)};
        const nokkelData = {json.dumps(nokkel_data, ensure_ascii=False)};

        // Navigation
        function showPage(page) {{
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.sidebar').forEach(s => s.style.display = 'none');
            document.querySelectorAll('.nav button').forEach(b => b.classList.remove('active'));

            document.getElementById('page-' + page).classList.add('active');
            event.target.classList.add('active');

            if (page === 'forsinkelser') {{
                document.getElementById('sidebar-forsinkelser').style.display = 'block';
                updateKoChart();
            }} else if (page === 'reisestatistikk') {{
                document.getElementById('sidebar-reisestatistikk').style.display = 'block';
                updateReiserChart();
            }} else if (page === 'nokkeltall') {{
                document.getElementById('sidebar-nokkeltall').style.display = 'block';
                updateNokkelChart();
            }}
        }}

        // Navigering fra hjem-kort
        function navigateTo(page) {{
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.sidebar').forEach(s => s.style.display = 'none');
            document.querySelectorAll('.nav button').forEach(b => b.classList.remove('active'));

            document.getElementById('page-' + page).classList.add('active');

            // Finn og marker riktig navigasjonsknapp
            const navButtons = document.querySelectorAll('.nav button');
            navButtons.forEach(btn => {{
                if (btn.getAttribute('onclick') === "showPage('" + page + "')") {{
                    btn.classList.add('active');
                }}
            }});

            if (page === 'forsinkelser') {{
                document.getElementById('sidebar-forsinkelser').style.display = 'block';
                updateKoChart();
            }} else if (page === 'reisestatistikk') {{
                document.getElementById('sidebar-reisestatistikk').style.display = 'block';
                updateReiserChart();
            }} else if (page === 'nokkeltall') {{
                document.getElementById('sidebar-nokkeltall').style.display = 'block';
                updateNokkelChart();
            }}
        }}

        // Kø/Forsinkelser chart
        function updateKoChart() {{
            const strekning = document.getElementById('strekning-ko').value;
            const visning = document.querySelector('input[name="visning"]:checked').value;
            const xakse = document.querySelector('input[name="xakse"]:checked').value;
            const tid = document.querySelector('input[name="tid"]:checked').value;

            let dataKey, xData, yData, xLabel, chartType;

            if (xakse === 'dato') {{
                dataKey = strekning + '_' + tid;
                if (!koData[dataKey]) {{
                    console.log('Ingen data for:', dataKey);
                    return;
                }}
                xData = koData[dataKey].datoer;
                yData = visning === 'ko' ? koData[dataKey].ko : koData[dataKey].forsinkelser;
                xLabel = 'Dato';
                chartType = 'scatter';
            }} else {{
                dataKey = strekning + '_' + tid + '_klokkeslett';
                if (!koData[dataKey]) {{
                    console.log('Ingen data for:', dataKey);
                    return;
                }}
                xData = koData[dataKey].klokkeslett;
                yData = visning === 'ko' ? koData[dataKey].ko : koData[dataKey].forsinkelser;
                xLabel = 'Klokkeslett';
                chartType = 'bar';
            }}

            const yLabel = visning === 'ko' ? 'Kø (min/km)' : 'Forsinkelser (min)';
            const title = (visning === 'ko' ? 'Kø' : 'Forsinkelser buss') + ' - ' + strekning.toLowerCase() + ' (' + tid.toLowerCase() + ')';

            const trace = {{
                x: xData,
                y: yData,
                type: chartType,
                mode: chartType === 'scatter' ? 'lines' : undefined,
                marker: {{ color: '#636EFA' }},
                line: {{ color: '#636EFA' }}
            }};

            const layout = {{
                title: title,
                xaxis: {{ 
                    title: xLabel, 
                    tickangle: -45,
                    type: 'category'
                }},
                yaxis: {{ title: yLabel, rangemode: 'tozero' }},
                hovermode: 'x unified'
            }};

            Plotly.newPlot('ko-chart', [trace], layout, {{responsive: true}});
        }}

        // Reisestatistikk chart
        function updateReiserChart() {{
            const strekning = document.getElementById('strekning-reiser').value;
            const data = reiserData[strekning];
            if (!data) return;

            const colors = {{
                'Bil': '#636EFA',
                'Buss': '#EF553B',
                'Sykkel': '#00CC96',
                'Gange': '#AB63FA',
                'Tog': '#FFA15A'
            }};

            const traces = [
                {{ name: 'Bil', x: data.kvartaler, y: data.bil, type: 'scatter', mode: 'lines', line: {{ color: colors['Bil'] }} }},
                {{ name: 'Buss', x: data.kvartaler, y: data.buss, type: 'scatter', mode: 'lines', line: {{ color: colors['Buss'] }} }},
                {{ name: 'Sykkel', x: data.kvartaler, y: data.sykkel, type: 'scatter', mode: 'lines', line: {{ color: colors['Sykkel'] }} }},
                {{ name: 'Gange', x: data.kvartaler, y: data.gange, type: 'scatter', mode: 'lines', line: {{ color: colors['Gange'] }} }},
                {{ name: 'Tog', x: data.kvartaler, y: data.tog, type: 'scatter', mode: 'lines', line: {{ color: colors['Tog'] }} }}
            ];

            const layout = {{
                title: 'Reisestatistikk - ' + strekning + ' (1000 reiser per kvartal)',
                xaxis: {{ title: 'Kvartal', tickangle: -45, type: 'category' }},
                yaxis: {{ title: 'Antall reiser (1000 per kvartal)', rangemode: 'tozero' }},
                hovermode: 'x unified',
                legend: {{ title: {{ text: 'Transportmiddel' }} }}
            }};

            Plotly.newPlot('reiser-chart', traces, layout, {{responsive: true}});
        }}

        // Global variabel for CSV-eksport
        let csvExportData = [];

        // Funksjon for å beregne sentrert glidende gjennomsnitt
        function beregnGlidendeGjennomsnitt(values, windowSize) {{
            const result = [];
            const halfWindow = Math.floor(windowSize / 2);

            for (let i = 0; i < values.length; i++) {{
                // Beregn start og slutt for vinduet (sentrert)
                let start = Math.max(0, i - halfWindow);
                let end = Math.min(values.length - 1, i + halfWindow);

                // Samle verdier i vinduet (ignorer null/undefined)
                let sum = 0;
                let count = 0;
                for (let j = start; j <= end; j++) {{
                    if (values[j] != null && !isNaN(values[j])) {{
                        sum += values[j];
                        count++;
                    }}
                }}

                // Beregn gjennomsnitt hvis vi har minst 1 verdi
                if (count > 0) {{
                    result.push(Math.round(sum / count * 100) / 100);
                }} else {{
                    result.push(null);
                }}
            }}

            return result;
        }}

        // Nøkkeltall reiser chart
        function updateNokkelChart() {{
            const omradeFraSelect = document.getElementById('omrade-fra');
            const omradeTilSelect = document.getElementById('omrade-til');
            const tidNokkel = document.querySelector('input[name="tid-nokkel"]:checked').value;
            const ukedagNokkel = document.querySelector('input[name="ukedag-nokkel"]:checked').value;

            // Hent valgte områder (rå valg fra dropdown)
            let fraValg = Array.from(omradeFraSelect.selectedOptions).map(o => o.value);
            let tilValg = Array.from(omradeTilSelect.selectedOptions).map(o => o.value);

            const fraAlleValgt = fraValg.includes('Alle') || fraValg.length === 0;
            const tilAlleValgt = tilValg.includes('Alle') || tilValg.length === 0;

            // Bestem hvilke områder som skal brukes for filtrering
            let omraderFra = fraAlleValgt ? nokkelData.omrader_fra : fraValg;
            let omraderTil = tilAlleValgt ? nokkelData.omrader_til : tilValg;

            // Bestem om vi skal splitte til flere linjer
            // Prioriter fra-områder hvis begge har flervalg
            let splitPå = null;
            let splitOmrader = [];

            if (!fraAlleValgt && fraValg.length > 1) {{
                splitPå = 'fra';
                splitOmrader = fraValg;
            }} else if (!tilAlleValgt && tilValg.length > 1) {{
                splitPå = 'til';
                splitOmrader = tilValg;
            }}

            // Filtrer data
            let filtered = nokkelData.records.filter(r => {{
                const fraMatch = omraderFra.includes(r.delomrade_fra);
                const tilMatch = omraderTil.includes(r.delomrade_til);
                const tidMatch = tidNokkel === 'Alle' || r.time_of_day === tidNokkel;
                const ukedagMatch = ukedagNokkel === 'Alle' || r.weekday_indicator === ukedagNokkel;
                return fraMatch && tilMatch && tidMatch && ukedagMatch;
            }});

            const traces = [];
            csvExportData = [];
            const farger = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52'];

            if (splitPå === 'fra') {{
                // Flere linjer - én per fra-område
                splitOmrader.forEach((omrade, idx) => {{
                    const omradeFiltered = filtered.filter(r => r.delomrade_fra === omrade);

                    // Aggreger per kvartal
                    const kvartalSum = {{}};
                    omradeFiltered.forEach(r => {{
                        if (!kvartalSum[r.kvartal]) {{
                            kvartalSum[r.kvartal] = 0;
                        }}
                        kvartalSum[r.kvartal] += r.reiser || 0;
                    }});

                    const sortedKvartaler = nokkelData.kvartaler.filter(k => kvartalSum[k] !== undefined);
                    const yValues = sortedKvartaler.map(k => Math.round(kvartalSum[k] * 100) / 100);

                    // Beregn trend ETTER aggregering
                    const trendValues = beregnGlidendeGjennomsnitt(yValues, 5);

                    const farge = farger[idx % farger.length];

                    // Rådata som punkter (uten legend)
                    traces.push({{
                        x: sortedKvartaler,
                        y: yValues,
                        type: 'scatter',
                        mode: 'markers',
                        name: omrade,
                        marker: {{ color: farge, size: 8, opacity: 0.6 }},
                        showlegend: false
                    }});

                    // Trend som linje
                    traces.push({{
                        x: sortedKvartaler,
                        y: trendValues,
                        type: 'scatter',
                        mode: 'lines',
                        name: omrade,
                        line: {{ color: farge, width: 2, shape: 'spline', smoothing: 1.0 }},
                        connectgaps: true
                    }});

                    // Lagre for CSV
                    const tilOmraderTekst = tilAlleValgt ? 'Alle' : tilValg.join(', ');
                    sortedKvartaler.forEach((k, i) => {{
                        csvExportData.push({{
                            område_fra: omrade,
                            område_til: tilOmraderTekst,
                            kvartal: k,
                            rådata: yValues[i],
                            trend: trendValues[i]
                        }});
                    }});
                }});
            }} else if (splitPå === 'til') {{
                // Flere linjer basert på til-områder
                splitOmrader.forEach((omrade, idx) => {{
                    const omradeFiltered = filtered.filter(r => r.delomrade_til === omrade);

                    // Aggreger per kvartal
                    const kvartalSum = {{}};
                    omradeFiltered.forEach(r => {{
                        if (!kvartalSum[r.kvartal]) {{
                            kvartalSum[r.kvartal] = 0;
                        }}
                        kvartalSum[r.kvartal] += r.reiser || 0;
                    }});

                    const sortedKvartaler = nokkelData.kvartaler.filter(k => kvartalSum[k] !== undefined);
                    const yValues = sortedKvartaler.map(k => Math.round(kvartalSum[k] * 100) / 100);

                    // Beregn trend ETTER aggregering
                    const trendValues = beregnGlidendeGjennomsnitt(yValues, 5);

                    const farge = farger[idx % farger.length];

                    // Rådata som punkter (uten legend)
                    traces.push({{
                        x: sortedKvartaler,
                        y: yValues,
                        type: 'scatter',
                        mode: 'markers',
                        name: omrade,
                        marker: {{ color: farge, size: 8, opacity: 0.6 }},
                        showlegend: false
                    }});

                    // Trend som linje
                    traces.push({{
                        x: sortedKvartaler,
                        y: trendValues,
                        type: 'scatter',
                        mode: 'lines',
                        name: omrade,
                        line: {{ color: farge, width: 2, shape: 'spline', smoothing: 1.0 }},
                        connectgaps: true
                    }});

                    // Lagre for CSV
                    const fraOmraderTekst = fraAlleValgt ? 'Alle' : fraValg.join(', ');
                    sortedKvartaler.forEach((k, i) => {{
                        csvExportData.push({{
                            område_fra: fraOmraderTekst,
                            område_til: omrade,
                            kvartal: k,
                            rådata: yValues[i],
                            trend: trendValues[i]
                        }});
                    }});
                }});
            }} else {{
                // Én samlet linje
                const kvartalSum = {{}};
                filtered.forEach(r => {{
                    if (!kvartalSum[r.kvartal]) {{
                        kvartalSum[r.kvartal] = 0;
                    }}
                    kvartalSum[r.kvartal] += r.reiser || 0;
                }});

                const sortedKvartaler = nokkelData.kvartaler.filter(k => kvartalSum[k] !== undefined);
                const yValues = sortedKvartaler.map(k => Math.round(kvartalSum[k] * 100) / 100);

                // Beregn trend ETTER aggregering
                const trendValues = beregnGlidendeGjennomsnitt(yValues, 5);

                traces.push({{
                    x: sortedKvartaler,
                    y: yValues,
                    type: 'scatter',
                    mode: 'markers',
                    name: 'Rådata',
                    marker: {{ color: '#636EFA', size: 8, opacity: 0.6 }},
                    showlegend: false
                }});

                traces.push({{
                    x: sortedKvartaler,
                    y: trendValues,
                    type: 'scatter',
                    mode: 'lines',
                    name: 'Trend',
                    line: {{ color: '#636EFA', width: 2, shape: 'spline', smoothing: 1.0 }},
                    connectgaps: true
                }});

                // Lagre for CSV
                const fraOmraderTekst = fraAlleValgt ? 'Alle' : fraValg.join(', ');
                const tilOmraderTekst = tilAlleValgt ? 'Alle' : tilValg.join(', ');
                sortedKvartaler.forEach((k, i) => {{
                    csvExportData.push({{
                        område_fra: fraOmraderTekst,
                        område_til: tilOmraderTekst,
                        kvartal: k,
                        rådata: yValues[i],
                        trend: trendValues[i]
                    }});
                }});
            }}

            const layout = {{
                title: 'Reisestrømmer i Asker kommune - sum reiser per kvartal',
                xaxis: {{ title: 'Kvartal', tickangle: -45, type: 'category' }},
                yaxis: {{ title: 'Antall reiser (1000 per kvartal)', rangemode: 'tozero' }},
                hovermode: 'x unified',
                legend: {{ x: 0, y: 1.15, orientation: 'h' }}
            }};

            Plotly.newPlot('nokkel-chart', traces, layout, {{responsive: true}});

            // Vis/skjul sankey-knapp basert på filter
            const sankeyBtn = document.getElementById('sankey-btn');
            if (fraAlleValgt && tilAlleValgt) {{
                sankeyBtn.style.display = 'none';
            }} else {{
                sankeyBtn.style.display = 'inline-block';
            }}
        }}

        // CSV eksport funksjon
        function exportCSV() {{
            if (csvExportData.length === 0) {{
                alert('Ingen data å eksportere');
                return;
            }}

            // Lag CSV-innhold
            const headers = ['Område fra', 'Område til', 'Kvartal', 'Rådata', 'Trend'];
            const csvContent = [
                headers.join(';'),
                ...csvExportData.map(row => [
                    row.område_fra,
                    row.område_til,
                    row.kvartal,
                    row.rådata != null ? String(row.rådata).replace('.', ',') : '',
                    row.trend != null ? String(row.trend).replace('.', ',') : ''
                ].join(';'))
            ].join('\\n');

            // Last ned fil med UTF-8 BOM for Excel
            const BOM = '\\uFEFF';
            const blob = new Blob([BOM + csvContent], {{ type: 'text/csv;charset=utf-8;' }});
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = 'reisestrommer_asker.csv';
            link.click();
        }}

        // Sankey modal funksjoner
        function openSankeyModal() {{
            const fraValg = Array.from(document.getElementById('omrade-fra').selectedOptions).map(o => o.value);
            const tilValg = Array.from(document.getElementById('omrade-til').selectedOptions).map(o => o.value);
            const fraAlleValgt = fraValg.includes('Alle') || fraValg.length === 0;
            const tilAlleValgt = tilValg.includes('Alle') || tilValg.length === 0;

            const fraLabel = document.getElementById('sankey-fra-label');
            const tilLabel = document.getElementById('sankey-til-label');
            const fraRadio = fraLabel.querySelector('input');
            const tilRadio = tilLabel.querySelector('input');

            // Vis/skjul radioknapper basert på filtervalg
            if (fraAlleValgt) {{
                fraLabel.classList.add('disabled');
                tilLabel.classList.remove('disabled');
                tilRadio.checked = true;
            }} else if (tilAlleValgt) {{
                tilLabel.classList.add('disabled');
                fraLabel.classList.remove('disabled');
                fraRadio.checked = true;
            }} else {{
                fraLabel.classList.remove('disabled');
                tilLabel.classList.remove('disabled');
            }}

            document.getElementById('sankey-modal').style.display = 'block';
            updateSankeyChart();
        }}

        function closeSankeyModal() {{
            document.getElementById('sankey-modal').style.display = 'none';
        }}

        // Lukk modal ved klikk utenfor
        window.onclick = function(event) {{
            const modal = document.getElementById('sankey-modal');
            if (event.target === modal) {{
                modal.style.display = 'none';
            }}
        }}

        function updateSankeyChart() {{
            const omradeFraSelect = document.getElementById('omrade-fra');
            const omradeTilSelect = document.getElementById('omrade-til');
            const retning = document.querySelector('input[name="sankey-retning"]:checked').value;

            // Hent valgte områder
            let omraderFra = Array.from(omradeFraSelect.selectedOptions).map(o => o.value);
            let omraderTil = Array.from(omradeTilSelect.selectedOptions).map(o => o.value);

            // Sjekk om "Alle" er valgt
            const fraAlleValgt = omraderFra.includes('Alle') || omraderFra.length === 0;
            const tilAlleValgt = omraderTil.includes('Alle') || omraderTil.length === 0;

            // Finn siste 4 kvartaler
            const sisteKvartaler = nokkelData.kvartaler.slice(-4);

            // Filtrer data for siste 4 kvartaler
            let filtered = nokkelData.records.filter(r => sisteKvartaler.includes(r.kvartal));

            // Aggreger reiser per fra-til kombinasjon
            const strommer = {{}};
            let title = '';

            if (retning === 'fra') {{
                // Fra valgte områder til andre
                filtered.filter(r => omraderFra.includes(r.delomrade_fra)).forEach(r => {{
                    const key = r.delomrade_fra + '|' + r.delomrade_til;
                    if (!strommer[key]) {{
                        strommer[key] = {{ fra: r.delomrade_fra, til: r.delomrade_til, reiser: 0 }};
                    }}
                    strommer[key].reiser += r.reiser || 0;
                }});
                title = 'Reiser FRA valgte områder (topp 10 destinasjoner)';
            }} else {{
                // Fra andre til valgte områder
                filtered.filter(r => omraderTil.includes(r.delomrade_til)).forEach(r => {{
                    const key = r.delomrade_fra + '|' + r.delomrade_til;
                    if (!strommer[key]) {{
                        strommer[key] = {{ fra: r.delomrade_fra, til: r.delomrade_til, reiser: 0 }};
                    }}
                    strommer[key].reiser += r.reiser || 0;
                }});
                title = 'Reiser TIL valgte områder (topp 10 opprinnelser)';
            }}

            // Sorter og ta topp 10
            const topp10 = Object.values(strommer)
                .sort((a, b) => b.reiser - a.reiser)
                .slice(0, 10);

            if (topp10.length === 0) {{
                Plotly.newPlot('sankey-chart', [], {{
                    title: 'Ingen data for valgte filtre',
                    annotations: [{{
                        text: 'Velg områder i sidemenyen',
                        showarrow: false,
                        font: {{ size: 16 }}
                    }}]
                }});
                return;
            }}

            // Bygg Sankey-data
            const fraLabels = [...new Set(topp10.map(d => d.fra))];
            const tilLabels = [...new Set(topp10.map(d => d.til))];
            const alleLabels = [...fraLabels, ...tilLabels];

            // Farger - grønn for fra, blå for til
            const colors = [
                ...fraLabels.map(() => '#00CC96'),
                ...tilLabels.map(() => '#636EFA')
            ];

            // Link-data
            const sources = topp10.map(d => fraLabels.indexOf(d.fra));
            const targets = topp10.map(d => fraLabels.length + tilLabels.indexOf(d.til));
            const values = topp10.map(d => Math.round(d.reiser));

            // Link-farger med gradient-effekt
            const linkColors = topp10.map((d, i) => {{
                const hue = (i * 50) % 360;
                return `hsla(${{hue}}, 70%, 60%, 0.5)`;
            }});

            const trace = {{
                type: 'sankey',
                orientation: 'h',
                node: {{
                    pad: 20,
                    thickness: 30,
                    label: alleLabels,
                    color: colors
                }},
                link: {{
                    source: sources,
                    target: targets,
                    value: values,
                    color: linkColors
                }}
            }};

            const layout = {{
                title: title,
                font: {{ size: 12 }},
                annotations: [
                    {{ x: 0.0, y: 1.05, text: '<b>Fra</b>', showarrow: false, xref: 'paper', yref: 'paper', font: {{ color: '#00CC96' }} }},
                    {{ x: 1.0, y: 1.05, text: '<b>Til</b>', showarrow: false, xref: 'paper', yref: 'paper', font: {{ color: '#636EFA' }} }}
                ]
            }};

            Plotly.newPlot('sankey-chart', [trace], layout, {{responsive: true}});
        }}
    </script>
</body>
</html>
'''
    return html


def main():
    print("Laster kødata...")
    ko_data = load_and_process_ko_data("data/inndata_asker_ko.csv")
    print(f"  - {len(ko_data)} rader")
    print(f"  - Datoer: {ko_data['dato'].min()} til {ko_data['dato'].max()}")
    print(f"  - Strekninger: {ko_data['stop_name'].nunique()}")

    print("\nLaster reisedata...")
    reiser_data = load_and_process_reiser_data("data/inndata_asker_reiser.csv")
    print(f"  - {len(reiser_data)} rader")

    print("\nLaster nøkkeltalldata...")
    nokkel_df = load_and_process_nokkel_data("data/inndata_asker_nokkel.csv")
    nokkel_data = prepare_nokkel_data(nokkel_df)
    print(f"  - {len(nokkel_df)} rader")
    print(f"  - Områder fra: {len(nokkel_data['omrader_fra'])}")
    print(f"  - Områder til: {len(nokkel_data['omrader_til'])}")
    print(f"  - Tidsperioder: {len(nokkel_data['tider'])}")

    print("\nAggregerer kødata...")
    ko_aggregated = aggregate_ko_data(ko_data)
    print(f"  - {len(ko_aggregated)} datasett generert")

    print("\nGenererer HTML...")
    html = generate_html(ko_data, reiser_data, ko_aggregated, nokkel_data)

    import os
    os.makedirs("docs", exist_ok=True)

    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nFerdig! Generert: docs/index.html")
    print(f"Filstørrelse: {len(html) / 1024:.1f} KB")
    print("\nFor å publisere på GitHub Pages:")
    print("1. git add docs/")
    print("2. git commit -m 'Oppdatert dashboard'")
    print("3. git push")
    print("4. I GitHub: Settings → Pages → Source: 'Deploy from branch' → Branch: main, Folder: /docs")


if __name__ == "__main__":
    main()