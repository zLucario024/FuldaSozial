"""
Ortsteile-Verwaltung fuer rnfulda.de
======================================
Bearbeitet ortsteile_master.json und synchronisiert die Aenderungen
automatisch in alle 4 Codestellen:
  - index.html               -> ORTSTEILE_MAPPING
  - fulda_news_aggregator.py -> BEKANNTE_REGIONEN + ORTSTEILE_TO_GEMEINDE
  - api.py                   -> BEKANNTE_REGIONEN

Verwendung:
  python manage_ortsteile.py          # Interaktives Menue
  python manage_ortsteile.py sync     # Nur synchronisieren
  python manage_ortsteile.py list     # Alle Ortsteile ausgeben
"""

import json
import re
import sys
from pathlib import Path

BASE_DIR  = Path(__file__).parent
MASTER    = BASE_DIR / "ortsteile_master.json"
AGG_FILE  = BASE_DIR / "fulda_news_aggregator.py"
API_FILE  = BASE_DIR / "api.py"
HTML_FILE = BASE_DIR / "index.html"

# Reihenfolge der Gemeinden (fest, nicht aendern)
GEMEINDE_ORDER = [
    "fulda", "huenfeld", "kuenzell", "petersberg", "neuhof", "eichenzell",
    "flieden", "burghaun", "grossenlueder", "hilders", "hofbieber", "gersfeld",
    "tann", "eiterfeld", "rasdorf", "dipperz", "ebersburg", "ehrenberg",
    "hosenfeld", "kalbach", "nuesttal", "poppenhausen", "bad salzschlirf",
]

# Schluessel im JSON (mit Umlauten) in derselben Reihenfolge
GEMEINDE_KEYS = [
    "fulda", "hünfeld", "künzell", "petersberg", "neuhof", "eichenzell",
    "flieden", "burghaun", "großenlüder", "hilders", "hofbieber", "gersfeld",
    "tann", "eiterfeld", "rasdorf", "dipperz", "ebersburg", "ehrenberg",
    "hosenfeld", "kalbach", "nüsttal", "poppenhausen", "bad salzschlirf",
]

GEMEINDE_ANZEIGE = {
    "fulda":         "Stadt Fulda",
    "hünfeld":       "Stadt Huenfeld",
    "gersfeld":      "Stadt Gersfeld (Rhoen)",
    "tann":          "Gemeinde Tann (Rhoen)",
    "ehrenberg":     "Gemeinde Ehrenberg (Rhoen)",
    "poppenhausen":  "Gemeinde Poppenhausen (Wasserkuppe)",
    "bad salzschlirf": "Gemeinde Bad Salzschlirf",
}

def gemeinde_anzeige(g):
    if g in GEMEINDE_ANZEIGE:
        return GEMEINDE_ANZEIGE[g]
    return "Gemeinde " + g.title()

def ortsteil_label_py(g):
    """Kommentar-Label fuer Python-Code."""
    if g == "fulda":
        return "Stadtteile Fulda"
    titel = g.title()
    return f"Ortsteile {titel}"

def ortsteil_label_js(g):
    return f"// {gemeinde_anzeige(g)}"

# ---- Laden / Speichern ------------------------------------------------------

def laden():
    with open(MASTER, encoding="utf-8") as f:
        return json.load(f)

def speichern(daten):
    with open(MASTER, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    print("  [OK] ortsteile_master.json gespeichert")

# ---- Code-Generierung -------------------------------------------------------

def _py_wrap(items, indent=4):
    """Ortsteile als Python-Tupel-Zeilen, 6 Eintraege pro Zeile."""
    pad = " " * indent
    lines = []
    for i in range(0, len(items), 6):
        chunk = items[i:i+6]
        lines.append(pad + ", ".join(f"'{x}'" for x in chunk) + ",")
    return "\n".join(lines)

def _js_wrap(items, gemeinde, indent=2):
    """Ortsteile als JS-Objekt-Eintraege, 4 Eintraege pro Zeile."""
    pad = " " * indent
    lines = []
    for i in range(0, len(items), 4):
        chunk = items[i:i+4]
        lines.append(pad + ",".join(f"'{x}':'{gemeinde}'" for x in chunk) + ",")
    return "\n".join(lines)

def _dict_wrap(items, gemeinde, indent=4):
    """Ortsteile als Python-Dict-Zeilen, 4 Eintraege pro Zeile."""
    pad = " " * indent
    lines = []
    for i in range(0, len(items), 4):
        chunk = items[i:i+4]
        lines.append(pad + ", ".join(f"'{x}': '{gemeinde}'" for x in chunk) + ",")
    return "\n".join(lines)

def gen_bekannte_regionen_block(daten):
    """Erzeugt den Ortsteil-Block fuer BEKANNTE_REGIONEN (Python)."""
    parts = []
    for g in GEMEINDE_KEYS:
        ortsteile = sorted(daten.get(g, []))
        if not ortsteile:
            continue
        label = ortsteil_label_py(g)
        parts.append(f"    # {label}")
        parts.append(_py_wrap(ortsteile))
    return "\n".join(parts)

def gen_ortsteile_to_gemeinde(daten):
    """Erzeugt den Inhalt von ORTSTEILE_TO_GEMEINDE (Python-Dict)."""
    parts = []
    for g in GEMEINDE_KEYS:
        ortsteile = sorted(daten.get(g, []))
        if not ortsteile:
            continue
        label = ortsteil_label_py(g)
        parts.append(f"    # {label}")
        parts.append(_dict_wrap(ortsteile, g))
    return "\n".join(parts)

def gen_ortsteile_mapping(daten):
    """Erzeugt den Inhalt von ORTSTEILE_MAPPING (JavaScript)."""
    parts = []
    for g in GEMEINDE_KEYS:
        ortsteile = sorted(daten.get(g, []))
        if not ortsteile:
            continue
        parts.append(f"  {ortsteil_label_js(g)}")
        parts.append(_js_wrap(ortsteile, g))
    return "\n".join(parts)

# ---- Datei-Patches ----------------------------------------------------------

def patch_bekannte_regionen(pfad, daten):
    """Ersetzt den Ortsteil-Block in BEKANNTE_REGIONEN.
    Nutzt Lookahead damit die schliessende Klammer erhalten bleibt."""
    text = pfad.read_text(encoding="utf-8")
    block = gen_bekannte_regionen_block(daten)
    # Matcht alles von "# Stadtteile Fulda" bis direkt vor der Zeile mit nur ")" oder "}"
    pattern = r'    # Stadtteile Fulda\n.*?(?=\n[ \t]*[)\}])'
    neu, n = re.subn(pattern, block, text, count=1, flags=re.DOTALL)
    if n == 0:
        print(f"  [!!] WARNUNG: BEKANNTE_REGIONEN-Block nicht gefunden in {pfad.name}")
        return False
    pfad.write_text(neu, encoding="utf-8")
    return True

def patch_ortsteile_to_gemeinde(pfad, daten):
    """Ersetzt den Inhalt von ORTSTEILE_TO_GEMEINDE."""
    text = pfad.read_text(encoding="utf-8")
    block = gen_ortsteile_to_gemeinde(daten)
    pattern = r'(ORTSTEILE_TO_GEMEINDE = \{\n).*?(\n\})'
    replacement = r'\g<1>' + block + r'\n\g<2>'
    neu, n = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if n == 0:
        print(f"  [!!] WARNUNG: ORTSTEILE_TO_GEMEINDE nicht gefunden in {pfad.name}")
        return False
    pfad.write_text(neu, encoding="utf-8")
    return True

def patch_ortsteile_mapping(pfad, daten):
    """Ersetzt den Inhalt von ORTSTEILE_MAPPING in index.html."""
    text = pfad.read_text(encoding="utf-8")
    block = gen_ortsteile_mapping(daten)
    pattern = r'(const ORTSTEILE_MAPPING = \{\n).*?(\n\};)'
    replacement = r'\g<1>' + block + r'\n\g<2>'
    neu, n = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if n == 0:
        print(f"  [!!] WARNUNG: ORTSTEILE_MAPPING nicht gefunden in {pfad.name}")
        return False
    pfad.write_text(neu, encoding="utf-8")
    return True

# ---- Sync -------------------------------------------------------------------

def sync(daten=None):
    if daten is None:
        daten = laden()
    print("\nSynchronisiere alle Dateien...")
    ergebnisse = {
        "fulda_news_aggregator.py (BEKANNTE_REGIONEN)":    patch_bekannte_regionen(AGG_FILE, daten),
        "fulda_news_aggregator.py (ORTSTEILE_TO_GEMEINDE)": patch_ortsteile_to_gemeinde(AGG_FILE, daten),
        "api.py (BEKANNTE_REGIONEN)":                       patch_bekannte_regionen(API_FILE, daten),
        "index.html (ORTSTEILE_MAPPING)":                   patch_ortsteile_mapping(HTML_FILE, daten),
    }
    print()
    alle_ok = True
    for name, ok in ergebnisse.items():
        symbol = "[OK]" if ok else "[!!]"
        print(f"  {symbol} {name}")
        if not ok:
            alle_ok = False
    if alle_ok:
        print("\n  Alle 4 Stellen erfolgreich synchronisiert.")
    else:
        print("\n  Synchronisierung unvollstaendig — bitte Fehlermeldungen pruefen.")

# ---- Interaktives Menue -----------------------------------------------------

def eingabe(prompt, leer_ok=False):
    while True:
        v = input(prompt).strip()
        if v or leer_ok:
            return v
        print("  (Eingabe darf nicht leer sein)")

def gemeinde_waehlen(daten):
    print("\nGemeinden:")
    for i, g in enumerate(GEMEINDE_KEYS, 1):
        n = len(daten.get(g, []))
        print(f"  [{i:2}] {gemeinde_anzeige(g):38} ({n} Ortsteile)")
    while True:
        auswahl = eingabe("Nummer waehlen: ")
        try:
            idx = int(auswahl) - 1
            if 0 <= idx < len(GEMEINDE_KEYS):
                return GEMEINDE_KEYS[idx]
        except ValueError:
            pass
        print("  Ungueltige Eingabe.")

def ortsteile_anzeigen(daten, gemeinde):
    ortsteile = sorted(daten.get(gemeinde, []))
    print(f"\n  {gemeinde_anzeige(gemeinde)} -- {len(ortsteile)} Ortsteil(e):")
    if ortsteile:
        for o in ortsteile:
            print(f"    - {o}")
    else:
        print("    (keine)")

def ortsteil_hinzufuegen(daten, gemeinde):
    name = eingabe(f"  Neuer Ortsteil fuer {gemeinde_anzeige(gemeinde)}: ").lower()
    lst = daten.setdefault(gemeinde, [])
    if name in lst:
        print(f"  '{name}' ist bereits vorhanden.")
        return
    for g, ortsteile in daten.items():
        if g != gemeinde and name in ortsteile:
            print(f"  WARNUNG: '{name}' ist bereits Ortsteil von {gemeinde_anzeige(g)}!")
            if eingabe("  Trotzdem hinzufuegen? (j/n): ").lower() != "j":
                return
    lst.append(name)
    print(f"  '{name}' hinzugefuegt.")

def ortsteil_entfernen(daten, gemeinde):
    ortsteile = sorted(daten.get(gemeinde, []))
    if not ortsteile:
        print("  Keine Ortsteile vorhanden.")
        return
    ortsteile_anzeigen(daten, gemeinde)
    name = eingabe("  Zu entfernender Ortsteil: ").lower()
    if name not in daten.get(gemeinde, []):
        print(f"  '{name}' nicht gefunden.")
        return
    daten[gemeinde].remove(name)
    print(f"  '{name}' entfernt.")

def alle_ausgeben(daten):
    print()
    gesamt = 0
    for g in GEMEINDE_KEYS:
        ortsteile = sorted(daten.get(g, []))
        gesamt += len(ortsteile)
        print(f"  {gemeinde_anzeige(g):40} {len(ortsteile):3} Ortsteile")
        if "--detail" in sys.argv:
            for o in ortsteile:
                print(f"      - {o}")
    print(f"\n  Gesamt: {gesamt} Ortsteile in {len(GEMEINDE_KEYS)} Gemeinden")

def menue():
    print()
    print("=" * 52)
    print("  Ortsteile-Verwaltung -- rnfulda.de")
    print("=" * 52)
    daten = laden()
    gemeinde = None

    while True:
        print()
        if gemeinde:
            n = len(daten.get(gemeinde, []))
            print(f"  Gemeinde: {gemeinde_anzeige(gemeinde)} ({n} Ortsteile)")
        print("  [1] Gemeinde waehlen")
        if gemeinde:
            print("  [2] Ortsteile anzeigen")
            print("  [3] Ortsteil hinzufuegen")
            print("  [4] Ortsteil entfernen")
        print("  [5] Alle Gemeinden + Anzahl anzeigen")
        print("  [6] Speichern und alle Dateien synchronisieren")
        print("  [0] Beenden (ohne Sync)")
        print()
        wahl = eingabe("Auswahl: ", leer_ok=True)

        if wahl == "1":
            gemeinde = gemeinde_waehlen(daten)
        elif wahl == "2" and gemeinde:
            ortsteile_anzeigen(daten, gemeinde)
        elif wahl == "3" and gemeinde:
            ortsteil_hinzufuegen(daten, gemeinde)
        elif wahl == "4" and gemeinde:
            ortsteil_entfernen(daten, gemeinde)
        elif wahl == "5":
            alle_ausgeben(daten)
        elif wahl == "6":
            speichern(daten)
            sync(daten)
        elif wahl == "0":
            print("  Beendet. Aenderungen wurden NICHT synchronisiert.")
            break
        else:
            if wahl:
                print("  Ungueltige Auswahl.")

# ---- Einstiegspunkt ---------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "sync":
            sync()
        elif cmd == "list":
            alle_ausgeben(laden())
        elif cmd == "list" and "--detail" in sys.argv:
            alle_ausgeben(laden())
        else:
            print(f"Unbekannter Befehl: {cmd}")
            print("Verfuegbar: sync, list, list --detail")
            sys.exit(1)
    else:
        menue()
