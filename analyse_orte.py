import sqlite3

# Alle Orte im Landkreis Fulda und ihre Varianten
ORTE = {
    "Fulda": ["fulda", "fuldaer", "fuldas"],
    "Hünfeld": ["hünfeld", "hünfelder"],
    "Künzell": ["künzell", "künzeller"],
    "Petersberg": ["petersberg", "petersberger"],
    "Neuhof": ["neuhof", "neuhofer"],
    "Eichenzell": ["eichenzell", "eichenzeller"],
    "Flieden": ["flieden", "fliedener"],
    "Burghaun": ["burghaun", "burghauner"],
    "Großenlüder": ["großenlüder", "grossenlüder", "lüdertalbote"],
    "Hilders": ["hilders", "hilderser"],
    "Hofbieber": ["hofbieber", "hofbieberer"],
    "Gersfeld": ["gersfeld", "gersfelder"],
    "Tann": ["tann", "tanner"],
    "Eiterfeld": ["eiterfeld", "eiterfeldener"],
    "Rasdorf": ["rasdorf", "rasdorfer"],
    "Dipperz": ["dipperz", "dipperzer"],
    "Ebersburg": ["ebersburg", "ebersburger"],
    "Ehrenberg": ["ehrenberg", "ehrenberger"],
    "Hosenfeld": ["hosenfeld", "hosenfelder"],
    "Kalbach": ["kalbach", "kalbacher"],
    "Nüsttal": ["nüsttal", "nüsstaler"],
    "Poppenhausen": ["poppenhausen", "poppenhausener", "wasserkuppe"],
    "Bad Salzschlirf": ["bad salzschlirf", "salzschlirf"],
    # Ortsteile und bekannte Gebiete
    "Rhön": ["rhön", "rhöner", "rhönradler"],
    "Vogelsberg": ["vogelsberg"],
    "Johannesberg": ["johannesberg"],
    "Lehnerz": ["lehnerz", "barockstadt"],
    "Maberzell": ["maberzell"],
    "Horas": ["horas"],
}

conn = sqlite3.connect('fulda_news.db')
artikel = conn.execute('SELECT id, titel, tags, beschreibung FROM artikel').fetchall()
print(f"Analysiere {len(artikel)} Artikel...\n")

ergebnisse = {}

for ort, schlagwoerter in ORTE.items():
    treffer = []
    for id, titel, tags, beschreibung in artikel:
        text = ((titel or '') + ' ' + (tags or '') + ' ' + (beschreibung or '')).lower()        
        gefundene = [s for s in schlagwoerter if s in text]
        if gefundene:
            treffer.append((id, titel, gefundene))
    ergebnisse[ort] = treffer

# Ausgabe sortiert nach Anzahl Treffer
print("ORTE NACH HÄUFIGKEIT IN DER DATENBANK:")
print("=" * 55)
sortiert = sorted(ergebnisse.items(), key=lambda x: len(x[1]), reverse=True)

for ort, treffer in sortiert:
    if treffer:
        print(f"\n{ort}: {len(treffer)} Artikel")
        for id, titel, gefundene in treffer[:3]:
            print(f"  [{id}] {titel[:55]}...")
            print(f"       Gefunden: {', '.join(gefundene)}")

print("\n" + "=" * 55)
print("ORTE OHNE TREFFER:")
for ort, treffer in sortiert:
    if not treffer:
        print(f"  - {ort}")

conn.close()