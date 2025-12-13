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

    # Konverter dato
    df["dato"] = pd.to_datetime(df["dato"])
    df["dato_str"] = df["dato"].dt.strftime("%d.%m.%Y")

    # Håndter numeriske verdier
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

    # Lag sorteringsnøkkel
    df["kvartal_sort"] = df["kvartal"].str.replace("-", "").astype(int)
    df = df.sort_values("kvartal_sort").reset_index(drop=True)

    return df


def aggregate_ko_data(df):
    """Aggreger kødata for grafer"""
    aggregated = {}

    for tid_dag in ["Morgen", "Ettermiddag"]:
        df_tid = df[df["tid_dag"] == tid_dag].copy()

        if len(df_tid) == 0:
            continue

        # ===== ALLE STREKNINGER (vektet gjennomsnitt) =====
        # Per dato - vektet gjennomsnitt
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

        # Aggreger per dato for alle strekninger
        agg_alle_dato = df_tid.groupby("dato").apply(
            lambda g: pd.Series({
                "ko_min_km": weighted_avg_ko(g),
                "forsinkelser": weighted_avg_forsinkelser(g)
            })
        ).reset_index()
        agg_alle_dato = agg_alle_dato.sort_values("dato")
        agg_alle_dato["dato_str"] = agg_alle_dato["dato"].dt.strftime("%d.%m.%Y")

        key = f"Alle strekninger_{tid_dag}"
        aggregated[key] = {
            "datoer": agg_alle_dato["dato_str"].tolist(),
            "ko": [round(x, 3) if pd.notna(x) else None for x in agg_alle_dato["ko_min_km"].tolist()],
            "forsinkelser": [round(x, 3) if pd.notna(x) else None for x in agg_alle_dato["forsinkelser"].tolist()]
        }

        # Aggreger per klokkeslett for alle strekninger
        agg_alle_klokke = df_tid.groupby("klokkeslett").apply(
            lambda g: pd.Series({
                "ko_min_km": weighted_avg_ko(g),
                "forsinkelser": weighted_avg_forsinkelser(g)
            })
        ).reset_index()
        agg_alle_klokke = agg_alle_klokke.sort_values("klokkeslett")

        key = f"Alle strekninger_{tid_dag}_klokkeslett"
        aggregated[key] = {
            "klokkeslett": agg_alle_klokke["klokkeslett"].tolist(),
            "ko": [round(x, 3) if pd.notna(x) else None for x in agg_alle_klokke["ko_min_km"].tolist()],
            "forsinkelser": [round(x, 3) if pd.notna(x) else None for x in agg_alle_klokke["forsinkelser"].tolist()]
        }

        # ===== PER STREKNING =====
        for stop in df_tid["stop_name"].dropna().unique():
            df_stop = df_tid[df_tid["stop_name"] == stop]

            # Per dato (median per dag)
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

            # Per klokkeslett (median over alle datoer)
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


def generate_html(ko_data, reiser_data, ko_aggregated):
    """Generer HTML med embedded data og JavaScript"""

    # Legg til "Alle strekninger" først i listen
    strekninger_ko = ["Alle strekninger"] + sorted(ko_data["stop_name"].dropna().unique().tolist())
    strekninger_reiser = sorted(reiser_data["ID"].unique().tolist())
    kvartaler = reiser_data.sort_values("kvartal_sort")["kvartal"].unique().tolist()

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
        <button onclick="showPage('forsinkelser')">Forsinkelser</button>
        <button onclick="showPage('reisestatistikk')">Reisestatistikk</button>
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

        <div class="main">
            <!-- HJEM -->
            <div class="page active" id="page-hjem">
                <h2>Velkommen til Mobilitetsdashbordet</h2>
                <p style="margin: 20px 0;">
                    Dette dashbordet gir en oversikt over sentrale mobilitetsindikatorer for Asker kommune.
                    Her kan du følge med på utviklingen i kø, forsinkelser og reisemønstre over tid.
                </p>

                <div class="home-grid">
                    <div class="home-card">
                        <h3>📊 Forsinkelser</h3>
                        <p>Oversikt over kø og forsinkelser på utvalgte strekninger i Asker.</p>
                        <ul style="margin-top: 10px; margin-left: 20px;">
                            <li>Køindeks (min/km)</li>
                            <li>Forsinkelser for buss</li>
                            <li>Filtrer på tid og strekning</li>
                        </ul>
                    </div>
                    <div class="home-card">
                        <h3>🗺️ Kart</h3>
                        <p>Interaktivt kart over Asker sentrum.</p>
                        <ul style="margin-top: 10px; margin-left: 20px;">
                            <li>Trafikkmønstre til/fra sentrum</li>
                            <li>Gjennomfartstrafikk</li>
                            <li>Oversikt over køer</li>
                            <li>Soner og grids</li>
                        </ul>
                    </div>
                    <div class="home-card">
                        <h3>🚌 Reisestatistikk</h3>
                        <p>Statistikk over reiser og reisemønstre.</p>
                        <ul style="margin-top: 10px; margin-left: 20px;">
                            <li>Antall reiser per kvartal</li>
                            <li>Fordelt på transportmiddel</li>
                            <li>Filtrer på strekning</li>
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

        // Navigation
        function showPage(page) {{
            // Hide all pages and sidebars
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.sidebar').forEach(s => s.style.display = 'none');
            document.querySelectorAll('.nav button').forEach(b => b.classList.remove('active'));

            // Show selected page
            document.getElementById('page-' + page).classList.add('active');
            event.target.classList.add('active');

            // Show relevant sidebar
            if (page === 'forsinkelser') {{
                document.getElementById('sidebar-forsinkelser').style.display = 'block';
                updateKoChart();
            }} else if (page === 'reisestatistikk') {{
                document.getElementById('sidebar-reisestatistikk').style.display = 'block';
                updateReiserChart();
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

    print("\nAggregerer kødata...")
    ko_aggregated = aggregate_ko_data(ko_data)
    print(f"  - {len(ko_aggregated)} datasett generert")

    # Debug: vis noen nøkler
    print(f"  - Eksempel-nøkler: {list(ko_aggregated.keys())[:5]}")

    print("\nGenererer HTML...")
    html = generate_html(ko_data, reiser_data, ko_aggregated)

    # Lagre til docs/ for GitHub Pages
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