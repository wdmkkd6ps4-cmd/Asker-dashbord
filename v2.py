"""
v2.py

Bygger på generer_dashbord.py UTEN å endre den.
Eneste forskjell: på siden "Forsinkelser og køer" oppdateres Strekning-lista
dynamisk hver gang man bytter Kø/Forsinkelser eller Morgen/Ettermiddag, slik at
den kun viser strekninger som har minst én ikke-null verdi for det aktuelle valget.

Bruk:
    python v2.py
Output:
    docs/index.html   (samme plassering som generer_dashbord.py)
"""

import generer_dashbord as base

_orig_generate_html = base.generate_html


# JS som injiseres rett foer avsluttende </script>.
_INJECTED_JS = """
        // === v2: dynamisk strekningsliste for "Forsinkelser og koeer" ===
        const alleStrekninger = [...new Set(
            Object.keys(koData)
                .filter(k => !k.includes('_klokkeslett'))
                .filter(k => k.endsWith('_Morgen') || k.endsWith('_Ettermiddag'))
                .map(k => k.replace(/_(Morgen|Ettermiddag)$/, ''))
        )].filter(s => s !== 'Alle strekninger').sort();

        function harDataForValg(strekning, visning, tid) {
            const d = koData[strekning + '_' + tid];
            if (!d) return false;
            const arr = d[visning];
            return Array.isArray(arr) && arr.some(v => v !== null && v !== undefined);
        }

        function oppdaterStrekningsliste() {
            const sel = document.getElementById('strekning-ko');
            if (!sel) return;
            const visning = document.querySelector('input[name="visning"]:checked').value;
            const tid = document.querySelector('input[name="tid"]:checked').value;
            const tidligereValgt = Array.from(sel.selectedOptions).map(o => o.value);

            const gyldige = alleStrekninger.filter(s => harDataForValg(s, visning, tid));

            let opts = '<option value="Alle strekninger">Alle strekninger</option>';
            gyldige.forEach(s => { opts += '<option value="' + s + '">' + s + '</option>'; });
            sel.innerHTML = opts;

            // Behold tidligere valg som fortsatt finnes; ellers fall tilbake til "Alle strekninger"
            let beholdt = false;
            Array.from(sel.options).forEach(o => {
                if (tidligereValgt.includes(o.value)) { o.selected = true; beholdt = true; }
            });
            if (!beholdt) { sel.options[0].selected = true; }
        }

        // Overstyrer base-versjonen: oppdater ogsaa strekningslista ved bytte av visning
        function onVisningChange() {
            initStartdatoFilter();
            oppdaterStrekningsliste();
            updateKoChart();
        }

        document.addEventListener('DOMContentLoaded', oppdaterStrekningsliste);
"""


def _patch_html(html):
    # Tid-radioene (Morgen/Ettermiddag) skal ogsaa bygge strekningslista paa nytt
    erstatninger = [
        ('name="tid" value="Morgen" checked onchange="updateKoChart()"',
         'name="tid" value="Morgen" checked onchange="oppdaterStrekningsliste(); updateKoChart()"'),
        ('name="tid" value="Ettermiddag" onchange="updateKoChart()"',
         'name="tid" value="Ettermiddag" onchange="oppdaterStrekningsliste(); updateKoChart()"'),
    ]
    for gammel, ny in erstatninger:
        if gammel not in html:
            raise RuntimeError(f"Fant ikke forventet HTML-bit: {gammel!r}")
        html = html.replace(gammel, ny)

    anker = "    </script>\n</body>"
    if anker not in html:
        raise RuntimeError("Fant ikke ankerpunkt (</script>) for JS-injeksjon")
    html = html.replace(anker, _INJECTED_JS + "\n" + anker)
    return html


def generate_html(*args, **kwargs):
    return _patch_html(_orig_generate_html(*args, **kwargs))


# Monkeypatch slik at base.main() bruker den modifiserte HTML-genereringen
base.generate_html = generate_html


if __name__ == "__main__":
    base.main()
