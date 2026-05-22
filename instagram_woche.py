#!/usr/bin/env python3
"""
Generiert den wöchentlichen Instagram-Post "Fulda der Woche".

Aufruf:
    python instagram_woche.py              # laufende Woche bisher
    python instagram_woche.py --vorwoche   # abgeschlossene Vorwoche (für Montag-Post)
"""

import io
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Konstanten ─────────────────────────────────────────────────────────────────

KATEGORIE_EMOJI = {
    'Vorfälle':             '🚨',
    'Politik & Verwaltung': '🏛️',
    'Wirtschaft & Arbeit':  '💼',
    'Sport':                '⚽',
    'Kultur & Freizeit':    '🎭',
    'Bildung & Familie':    '📚',
    'Natur & Umwelt':       '🌿',
    'Verkehr & Bau':        '🚧',
    'Gesundheit':           '🏥',
    'Sonstiges':            '📰',
}

WAPPEN_NAMEN = {
    'fulda': 'Fulda', 'hünfeld': 'Hünfeld', 'künzell': 'Künzell',
    'petersberg': 'Petersberg', 'neuhof': 'Neuhof', 'eichenzell': 'Eichenzell',
    'flieden': 'Flieden', 'burghaun': 'Burghaun', 'großenlüder': 'Großenlüder',
    'hilders': 'Hilders', 'hofbieber': 'Hofbieber', 'gersfeld': 'Gersfeld',
    'tann': 'Tann', 'eiterfeld': 'Eiterfeld', 'rasdorf': 'Rasdorf',
    'dipperz': 'Dipperz', 'ebersburg': 'Ebersburg', 'ehrenberg': 'Ehrenberg',
    'hosenfeld': 'Hosenfeld', 'kalbach': 'Kalbach', 'nüsttal': 'Nüsttal',
    'poppenhausen': 'Poppenhausen', 'bad salzschlirf': 'Bad Salzschlirf',
    'landkreis-fulda': 'Landkreis Fulda',
}

_IGNORIERTE_REGIONEN = frozenset({'hessen', 'osthessen', 'bundesweit'})

# ── Kategorien-Keywords ────────────────────────────────────────────────────────

def _lade_kategorie_keywords() -> dict:
    pfad = os.path.join(os.path.dirname(__file__), 'kategorien.json')
    with open(pfad, 'r', encoding='utf-8') as f:
        return json.load(f)

_KEYWORDS = _lade_kategorie_keywords()


def kategorie_bestimmen(titel: str, tags: str) -> str:
    text = f"{titel or ''} {tags or ''}".lower()
    for phase in ('lock', 'strong', 'keys'):
        for kat, data in _KEYWORDS.items():
            if kat == 'Sonstiges':
                continue
            if any(k in text for k in (data.get(phase) or [])):
                return kat
    return 'Sonstiges'


# ── Veranstaltungs-Erkennung (portiert aus index.html) ────────────────────────

_VERANST_DATUM_RGX = [
    re.compile(r'\b\d{1,2}\.\s*(?:januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)\b', re.I),
    re.compile(r'\b\d{1,2}\.\d{1,2}\.(?:\d{2,4})?\b'),
    re.compile(r'\bum\s+\d{1,2}[:.h]\d{0,2}\s*uhr\b', re.I),
    re.compile(r'\b(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b', re.I),
    re.compile(r'\b(?:nächste[nrs]?|diese[nrs]?|kommende[nrs]?)\s+(?:woche|wochenende|monat)\b', re.I),
]

_VERANST_KEYS = [
    'veranstaltung', 'konzert', 'festival', 'ausstellung', 'theater', 'oper',
    'aufführung', 'vorstellung', 'lesung', 'vortrag', 'workshop', 'messe',
    'markt', 'flohmarkt', 'fest ', 'feier', 'open air', 'openair', 'kirmes',
    'kirmess', 'fastnacht', 'karneval', 'turnier', 'sportfest', 'lauf',
    'rennen', 'wanderung', 'exkursion', 'probe', 'einlass', 'beginn:',
    'ticket', 'eintritt frei', 'lädt ein', 'eingeladen',
    'tag der offenen tür', 'hoffest', 'sommerfest', 'stadtfest',
]

_MONAT_NR = {
    'januar': 1, 'februar': 2, 'märz': 3, 'april': 4, 'mai': 5, 'juni': 6,
    'juli': 7, 'august': 8, 'september': 9, 'oktober': 10, 'november': 11, 'dezember': 12,
}

# JS-style weekday index (0=Sonntag, 1=Montag … 6=Samstag) – spiegelt index.html
_TAG_JS = {
    'sonntag': 0, 'montag': 1, 'dienstag': 2, 'mittwoch': 3,
    'donnerstag': 4, 'freitag': 5, 'samstag': 6,
}


def _artikel_text(a: dict) -> str:
    return f"{a.get('titel','') or ''} {a.get('beschreibung','') or ''} {a.get('tags','') or ''}".lower()


def ist_veranstaltung(a: dict) -> bool:
    text = _artikel_text(a)
    return any(r.search(text) for r in _VERANST_DATUM_RGX) and any(k in text for k in _VERANST_KEYS)


def ist_vergangen(a: dict, heute: date) -> bool:
    """Portiert 1:1 aus veranstaltungsDatumIstVergangen() in index.html."""
    text = _artikel_text(a)

    # Wochentag + Monatsname: "Samstag, 24. Mai [2026]"
    m = re.search(
        r'\b(montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)[,\s]+'
        r'(\d{1,2})\.\s*(januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)'
        r'(?:\s+(\d{4}))?\b', text, re.I)
    if m:
        j = int(m.group(4)) if m.group(4) else heute.year
        try:
            return date(j, _MONAT_NR[m.group(3).lower()], int(m.group(2))) < heute
        except ValueError:
            pass

    # Datum + Monatsname: "15. Mai [2026]"
    m = re.search(
        r'\b(\d{1,2})\.\s*(januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)'
        r'(?:\s+(\d{4}))?\b', text, re.I)
    if m:
        j = int(m.group(3)) if m.group(3) else heute.year
        try:
            return date(j, _MONAT_NR[m.group(2).lower()], int(m.group(1))) < heute
        except ValueError:
            pass

    # Numerisch: "15.06." / "15.06.2026"
    m = re.search(r'\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})?\b', text)
    if m:
        j_raw = m.group(3)
        j = (2000 + int(j_raw)) if (j_raw and len(j_raw) == 2) else (int(j_raw) if j_raw else heute.year)
        try:
            return date(j, int(m.group(2)), int(m.group(1))) < heute
        except ValueError:
            pass

    # "kommenden/nächsten Wochentag" → definitiv zukünftig
    if re.search(r'\b(?:nächst(?:en|em|e)?|kommend(?:en|em|e)?)\s+'
                 r'(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b', text, re.I):
        return False

    # "letzten/vergangenen Wochentag" → vergangen
    if re.search(r'\b(?:letzt(?:en|em|e)?|vergangen(?:en|em)?)\s+'
                 r'(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b', text, re.I):
        return True

    # Wochentag allein → vergangen wenn Index kleiner als heutiger JS-Wochentag
    m = re.search(r'\b(montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b', text, re.I)
    if m:
        heute_js = (heute.weekday() + 1) % 7  # Python Mon=0 → JS Mon=1, Sun=0
        return _TAG_JS.get(m.group(1).lower(), -1) < heute_js

    # "nächste/kommende Woche/Wochenende/Monat" → zukünftig
    if re.search(r'\b(?:nächste[nrs]?|kommende[nrs]?)\s+(?:woche|wochenende|monat)\b', text, re.I):
        return False

    return False


# ── Cross-Source Event Clustering ──────────────────────────────────────────────

_STOPPWOERTER = frozenset({
    'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'eines', 'einem', 'einen',
    'ist', 'sind', 'wird', 'hat', 'haben', 'war', 'waren', 'wurde', 'wurden',
    'von', 'für', 'mit', 'aus', 'bei', 'nach', 'zum', 'zur', 'ins', 'ans',
    'und', 'oder', 'aber', 'doch', 'wenn', 'weil', 'dass', 'als', 'wie',
    'auf', 'an', 'zu', 'über', 'unter', 'durch', 'gegen', 'vor', 'seit',
    'auch', 'noch', 'schon', 'nur', 'nicht', 'mehr', 'sehr', 'neue', 'neuen',
    'laut', 'beim', 'gibt', 'gab', 'hatte', 'beim', 'zwei', 'drei', 'vier',
    'nach', 'beim', 'wird', 'gaben', 'haben',
})


def _schluesselwoerter(titel: str) -> frozenset:
    woerter = re.findall(r'[a-zäöüß]{4,}', titel.lower())
    return frozenset(w for w in woerter if w not in _STOPPWOERTER)


def top_multiquellen_events(rows: list, top_n: int = 3) -> list:
    """Findet Ereignisse, über die die meisten verschiedenen Quellen berichteten."""
    cluster_liste: list[list[dict]] = []

    for artikel in rows:
        kw = _schluesselwoerter(artikel['titel'])
        if len(kw) < 2:
            continue
        beste_gruppe = None
        bester_score = 1  # Minimum: mindestens 2 gemeinsame Wörter
        for gruppe in cluster_liste:
            ref_kw = _schluesselwoerter(gruppe[0]['titel'])
            gemeinsam = len(kw & ref_kw)
            if gemeinsam > bester_score:
                bester_score = gemeinsam
                beste_gruppe = gruppe
        if beste_gruppe is not None:
            beste_gruppe.append(artikel)
        else:
            cluster_liste.append([artikel])

    multi: list[dict] = []
    for gruppe in cluster_liste:
        quellen = sorted({a['quelle'] for a in gruppe})
        if len(quellen) >= 2:
            multi.append({
                'titel':   gruppe[0]['titel'],
                'quellen': quellen,
                'anzahl':  len(quellen),
            })

    multi.sort(key=lambda x: x['anzahl'], reverse=True)
    return multi[:top_n]


# ── Umami-Klick-Daten ─────────────────────────────────────────────────────────

_UMAMI_BASE    = 'https://api.umami.is/v1'
_UMAMI_SITE_ID = 'ff8bd343-419c-41c7-86fe-c96a60506d8a'


def umami_top_klicks(von: datetime, bis: datetime, top_n: int = 1) -> list:
    """Fragt Umami nach den meistgeklickten Artikeln im Zeitraum (Event: artikel-geklickt)."""
    api_key = os.getenv('UMAMI_API_KEY')
    if not api_key:
        return []
    start_ms = int(von.timestamp() * 1000)
    end_ms   = int(bis.timestamp() * 1000)
    url = (
        f"{_UMAMI_BASE}/websites/{_UMAMI_SITE_ID}/event-data/values"
        f"?startAt={start_ms}&endAt={end_ms}"
        f"&event=artikel-geklickt&propertyName=titel"
    )
    try:
        r = requests.get(url, headers={'x-umami-api-key': api_key, 'Accept': 'application/json'}, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            data = data.get('data', [])
        ergebnisse = [
            {'titel': row.get('value') or row.get('x', ''), 'klicks': row.get('total') or row.get('y', 0)}
            for row in data
        ]
        ergebnisse.sort(key=lambda x: x['klicks'], reverse=True)
        return ergebnisse[:top_n]
    except Exception as e:
        print(f"  [Umami] Fehler: {e}", file=sys.stderr)
        return []


# ── Hauptprogramm ──────────────────────────────────────────────────────────────

def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    vorwoche  = '--vorwoche' in sys.argv
    heute     = datetime.now()
    heute_d   = heute.date()
    wochentag = heute.weekday()  # 0=Mo

    if vorwoche:
        montag = heute - timedelta(days=wochentag + 7)
        von    = montag.replace(hour=0, minute=0, second=0, microsecond=0)
        bis    = von + timedelta(days=7)
    else:
        von = (heute - timedelta(days=wochentag)).replace(hour=0, minute=0, second=0, microsecond=0)
        bis = heute

    kw   = von.isocalendar()[1]
    jahr = von.year

    conn   = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Artikel der Woche
    cursor.execute("""
        SELECT titel, region, tags, quelle, beschreibung, datum, link
        FROM artikel
        WHERE datum >= %s AND datum < %s
        ORDER BY datum DESC
    """, (von.strftime('%Y-%m-%d %H:%M:%S'), bis.strftime('%Y-%m-%d %H:%M:%S')))
    rows = [dict(r) for r in cursor.fetchall()]

    # Breiteres Fenster für Veranstaltungs-Ankündigungen (14 Tage)
    vor14 = (heute - timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        SELECT titel, region, tags, quelle, beschreibung, datum, link
        FROM artikel
        WHERE datum >= %s AND datum < %s
        ORDER BY datum DESC
    """, (vor14, bis.strftime('%Y-%m-%d %H:%M:%S')))
    alle_recent = [dict(r) for r in cursor.fetchall()]

    cursor.close()
    conn.close()

    if not rows:
        print(f"Keine Artikel für KW {kw}/{jahr} gefunden.")
        return

    lokale = [r for r in rows if r.get('region') not in _IGNORIERTE_REGIONEN]
    gesamt = len(lokale)

    # Kategorien-Ranking (alle, ohne Sonstiges)
    kategorien: dict[str, int] = defaultdict(int)
    for r in lokale:
        kat = kategorie_bestimmen(r['titel'], r['tags'])
        kategorien[kat] += 1
    alle_kategorien = [
        (k, n) for k, n in sorted(kategorien.items(), key=lambda x: x[1], reverse=True)
        if k != 'Sonstiges'
    ]

    # Top-5-Gemeinden (ohne Fulda und ohne Landkreis-Gesamt)
    regionen: dict[str, int] = defaultdict(int)
    for r in lokale:
        reg = r.get('region')
        if reg and reg in WAPPEN_NAMEN and reg not in ('fulda', 'landkreis-fulda'):
            regionen[reg] += 1
    top_gemeinden = sorted(regionen.items(), key=lambda x: x[1], reverse=True)[:5]

    # Multi-Quellen-Events
    multi_events = top_multiquellen_events(lokale, top_n=3)

    # Meistgeklickter Artikel (Umami)
    top_klicks = umami_top_klicks(von, bis, top_n=1)

    # Bevorstehende Veranstaltungen
    upcoming = [
        a for a in alle_recent
        if ist_veranstaltung(a) and not ist_vergangen(a, heute_d)
    ][:2]

    # ── Caption bauen ──────────────────────────────────────────────────────────
    L = []

    L.append(f"📰 FULDA DER WOCHE — KW {kw}/{jahr}")
    L.append(f"📊 {gesamt} Meldungen aus dem Landkreis")
    L.append("")

    # Gemeinden
    L.append("📍 AKTIVSTE GEMEINDEN (ohne Fulda)")
    for i, (ort, anzahl) in enumerate(top_gemeinden, 1):
        L.append(f"{i}. {WAPPEN_NAMEN[ort]} – {anzahl}")
    L.append("")

    # Kategorie-Ranking
    L.append("📊 THEMEN DER WOCHE")
    for kat, anzahl in alle_kategorien:
        emoji = KATEGORIE_EMOJI.get(kat, '📰')
        L.append(f"{emoji} {kat}: {anzahl}")
    L.append("")

    # Meistgeklickter Artikel
    if top_klicks:
        tk = top_klicks[0]
        titel_kurz = tk['titel'][:65] + ('…' if len(tk['titel']) > 65 else '')
        L.append('🏆 MEISTGEKLICKTER ARTIKEL')
        L.append(f"👆 {titel_kurz}")
        L.append(f"   {tk['klicks']} Klicks diese Woche")
        L.append('')

    # Meistberichtete Ereignisse
    if multi_events:
        L.append("🗞️ MEISTBERICHTETE EREIGNISSE")
        for i, ev in enumerate(multi_events, 1):
            quellen_str = " · ".join(ev['quellen'])
            titel_kurz  = ev['titel'][:65] + ("…" if len(ev['titel']) > 65 else "")
            L.append(f"{i}. {titel_kurz}")
            L.append(f"   📡 {ev['anzahl']} Quellen: {quellen_str}")
        L.append("")

    # Bevorstehende Veranstaltungen
    if upcoming:
        L.append("📅 BALD IN DEINER REGION")
        for a in upcoming:
            ort_name   = WAPPEN_NAMEN.get(a.get('region') or '', '') or 'Landkreis Fulda'
            titel_kurz = a['titel'][:65] + ("…" if len(a['titel']) > 65 else "")
            L.append(f"📌 {titel_kurz}")
            L.append(f"   {ort_name}")
        L.append("")

    L.append("📲 Alle Meldungen kostenlos auf rnfulda.de")
    L.append("🔔 Push-Nachrichten für deine Gemeinde aktivieren!")
    L.append("")

    # Hashtags
    basis       = ["#Fulda", "#LandkreisFulda", "#Osthessen", "#RegioNachrichten",
                   "#NachrichtenFulda", "#Lokalnachrichten", "#Hessen"]
    basis_lower = {h.lower() for h in basis}
    extra: list[str] = []
    for ort, _ in top_gemeinden[:3]:
        tag = "#" + WAPPEN_NAMEN[ort].replace(" ", "").replace("-", "")
        if tag.lower() not in basis_lower:
            extra.append(tag)
    L.append(" ".join(basis + extra))

    caption = "\n".join(L)

    # ── Ausgabe ────────────────────────────────────────────────────────────────
    sep = "-" * 55
    print(sep)
    print(f"  Instagram KW {kw}/{jahr}  |  "
          f"{von.strftime('%d.%m.')}–{(bis - timedelta(seconds=1)).strftime('%d.%m.%Y')}")
    print(f"  Lokale Artikel: {gesamt}  |  Gesamt inkl. überregional: {len(rows)}")
    print(sep)
    print()
    print(caption)
    print()
    print(sep)
    print(f"  Canva / Grafik:")
    print(f"    Hero-Zahl : {gesamt}")
    print(f"    KW-Badge  : KW {kw}")
    print(f"    Top-Thema : {alle_kategorien[0][0] if alle_kategorien else '-'}")
    top_ort_name = WAPPEN_NAMEN.get(top_gemeinden[0][0], '-') if top_gemeinden else '-'
    print(f"    Top-Ort   : {top_ort_name} (excl. Fulda)")
    print(f"    Zeichen   : {len(caption)} / 2200 (Instagram-Limit)")
    print(sep)
    if not top_klicks:
        print()
        print("  [!] Kein UMAMI_API_KEY in .env → Klick-Daten übersprungen.")
        print("      Key unter cloud.umami.is → Profil → API Keys erstellen.")
    print(sep)


if __name__ == "__main__":
    main()
