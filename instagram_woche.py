#!/usr/bin/env python3
"""
Wochenbriefing – Datenbasis für Instagram-Posts.

Aufruf:
    python instagram_woche.py              # laufende Woche bisher
    python instagram_woche.py --vorwoche   # abgeschlossene Vorwoche (für Montag-Post)

Ausgabe: strukturierter Datenkatalog (kein fertiger Post) –
         Abschnitte einzeln kopierbar für eigene Zusammenstellung.
"""

import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
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

# Tags, die keine inhaltliche Bedeutung tragen (Ortsrauschen)
_ORT_BLACKLIST = frozenset(v.lower() for v in WAPPEN_NAMEN.values()) | frozenset({
    'landkreis fulda', 'osthessen', 'hessen', 'deutschland', 'fulda',
    'region fulda', 'landkreis',
})

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


# ── Veranstaltungs-Erkennung ───────────────────────────────────────────────────

_VERANST_DATUM_RGX = [
    re.compile(r'\b\d{1,2}\.\s*(?:januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)\b', re.I),
    re.compile(r'\b\d{1,2}\.\d{1,2}\.(?:\d{2,4})?\b'),
    re.compile(r'\bum\s+\d{1,2}[:.h]\d{0,2}\s*uhr\b', re.I),
    re.compile(r'\b(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b', re.I),
    re.compile(r'\b(?:nächste[nrs]?|diese[nrs]?|kommende[nrs]?)\s+(?:woche|wochenende|monat)\b', re.I),
    re.compile(r'\b(?:pfingstmontag|pfingstsonntag|ostermontag|ostersonntag|karfreitag|karsamstag|rosenm(?:on)?tag|heiligabend|silvester|neujahrstag?|himmelfahrt|fronleichnam|allerheiligen|reformationstag)\b', re.I),
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
    text = _artikel_text(a)

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

    m = re.search(
        r'\b(\d{1,2})\.\s*(januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)'
        r'(?:\s+(\d{4}))?\b', text, re.I)
    if m:
        j = int(m.group(3)) if m.group(3) else heute.year
        try:
            return date(j, _MONAT_NR[m.group(2).lower()], int(m.group(1))) < heute
        except ValueError:
            pass

    m = re.search(r'\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})?\b', text)
    if m:
        j_raw = m.group(3)
        j = (2000 + int(j_raw)) if (j_raw and len(j_raw) == 2) else (int(j_raw) if j_raw else heute.year)
        try:
            return date(j, int(m.group(2)), int(m.group(1))) < heute
        except ValueError:
            pass

    if re.search(r'\b(?:nächst(?:en|em|e)?|kommend(?:en|em|e)?)\s+'
                 r'(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b', text, re.I):
        return False

    if re.search(r'\b(?:letzt(?:en|em|e)?|vergangen(?:en|em)?)\s+'
                 r'(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b', text, re.I):
        return True

    m = re.search(r'\b(montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b', text, re.I)
    if m:
        heute_js = (heute.weekday() + 1) % 7
        return _TAG_JS.get(m.group(1).lower(), -1) < heute_js

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
    'laut', 'beim', 'gibt', 'gab', 'hatte', 'zwei', 'drei', 'vier',
    'nach', 'wird', 'gaben', 'haben',
})


def _schluesselwoerter(titel: str) -> frozenset:
    woerter = re.findall(r'[a-zäöüß]{4,}', titel.lower())
    return frozenset(w for w in woerter if w not in _STOPPWOERTER)


def top_multiquellen_events(rows: list, top_n: int = 5) -> list:
    cluster_liste: list[list[dict]] = []
    for artikel in rows:
        kw = _schluesselwoerter(artikel['titel'])
        if len(kw) < 2:
            continue
        beste_gruppe = None
        bester_score = 1
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
                'datum':   gruppe[0].get('datum', '')[:10],
            })

    multi.sort(key=lambda x: x['anzahl'], reverse=True)
    return multi[:top_n]


# ── Top-Tags ───────────────────────────────────────────────────────────────────

def top_tags_aus_artikeln(artikels: list, top_n: int = 25) -> list[tuple[str, int]]:
    zaehler: Counter = Counter()
    for a in artikels:
        tags_raw = a.get('tags', '') or ''
        for tag in re.split(r'[·,]', tags_raw):
            tag = tag.strip()
            if len(tag) >= 3 and tag.lower() not in _ORT_BLACKLIST:
                zaehler[tag] += 1
    return zaehler.most_common(top_n)


# ── Umami ──────────────────────────────────────────────────────────────────────

_UMAMI_BASE    = 'https://api.umami.is/v1'
_UMAMI_SITE_ID = 'ff8bd343-419c-41c7-86fe-c96a60506d8a'


def umami_top_klicks(von: datetime, bis: datetime, top_n: int = 5) -> list:
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


# ── Hilfsfunktionen Ausgabe ────────────────────────────────────────────────────

def _titel_kurz(t: str, n: int = 70) -> str:
    return t[:n] + ('…' if len(t) > n else '')

def _datum_kurz(iso: str) -> str:
    return iso[8:10] + '.' + iso[5:7] + '.' if iso and len(iso) >= 10 else ''

def _abschnitt(titel: str) -> None:
    print(f"\n── {titel} {'─' * max(0, 54 - len(titel))}")


# ── Hauptprogramm ──────────────────────────────────────────────────────────────

def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    vorwoche  = '--vorwoche' in sys.argv
    heute     = datetime.now()
    heute_d   = heute.date()
    wochentag = heute.weekday()

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

    cursor.execute("""
        SELECT titel, region, tags, quelle, beschreibung, datum, link
        FROM artikel
        WHERE datum >= %s AND datum < %s
        ORDER BY datum DESC
    """, (von.strftime('%Y-%m-%d %H:%M:%S'), bis.strftime('%Y-%m-%d %H:%M:%S')))
    rows = [dict(r) for r in cursor.fetchall()]

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

    lokale  = [r for r in rows if r.get('region') not in _IGNORIERTE_REGIONEN]
    gesamt  = len(lokale)
    bis_str = (bis - timedelta(seconds=1)).strftime('%d.%m.%Y')

    # ── Aggregationen ──────────────────────────────────────────────────────────

    # Kategorie je Artikel
    for r in lokale:
        r['_kat'] = kategorie_bestimmen(r['titel'], r['tags'])

    # Kategorie-Ranking
    kat_zaehler: Counter = Counter(r['_kat'] for r in lokale)
    kategorien_ranked = [
        (k, n) for k, n in kat_zaehler.most_common()
        if k != 'Sonstiges'
    ]
    # Sonstiges ans Ende
    if kat_zaehler.get('Sonstiges'):
        kategorien_ranked.append(('Sonstiges', kat_zaehler['Sonstiges']))

    # Gemeinden-Ranking (alle)
    reg_zaehler: Counter = Counter()
    for r in lokale:
        reg = r.get('region')
        if reg and reg in WAPPEN_NAMEN:
            reg_zaehler[reg] += 1

    # Matrix: Gemeinde → Kategorie → Artikel-Liste
    matrix: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for r in lokale:
        ort = r.get('region', '')
        if ort in WAPPEN_NAMEN:
            matrix[ort][r['_kat']].append(r)

    # Multi-Quellen-Events
    multi_events = top_multiquellen_events(lokale, top_n=5)

    # Top-Tags
    top_tags = top_tags_aus_artikeln(lokale, top_n=25)

    # Umami
    top_klicks = umami_top_klicks(von, bis, top_n=5)

    # Bevorstehende Veranstaltungen (14-Tage-Fenster)
    upcoming = [
        a for a in alle_recent
        if ist_veranstaltung(a) and not ist_vergangen(a, heute_d)
    ]

    # ── Ausgabe ────────────────────────────────────────────────────────────────
    SEP = '═' * 60

    print(SEP)
    print(f"  WOCHENBRIEFING  KW {kw}/{jahr}  │  {von.strftime('%d.%m.')}–{bis_str}")
    print(f"  Lokale Artikel: {gesamt}  │  gesamt inkl. überregional: {len(rows)}")
    print(SEP)

    # ── [1] GEMEINDEN ──────────────────────────────────────────────────────────
    _abschnitt('[1] GEMEINDEN — alle, nach Artikelzahl')
    for ort, n in reg_zaehler.most_common():
        name = WAPPEN_NAMEN[ort]
        balken = '█' * min(n, 30)
        print(f"  {name:<20}  {balken}  {n}")

    # ── [2] THEMEN ─────────────────────────────────────────────────────────────
    _abschnitt('[2] THEMEN — Kategorien dieser Woche')
    for kat, n in kategorien_ranked:
        emoji = KATEGORIE_EMOJI.get(kat, '📰')
        pct   = round(n / gesamt * 100) if gesamt else 0
        balken = '█' * min(n, 25)
        print(f"  {emoji} {kat:<25}  {balken}  {n} ({pct}%)")

    # ── [3] TOP STICHWORTE ─────────────────────────────────────────────────────
    _abschnitt('[3] TOP STICHWORTE — häufigste Tags aus Artikeln')
    if top_tags:
        max_n = top_tags[0][1]
        for tag, n in top_tags:
            balken = '▪' * round(n / max_n * 20)
            print(f"  {tag:<30}  {balken}  ×{n}")
    else:
        print("  (keine Tags vorhanden)")

    # ── [4] ARTIKEL JE GEMEINDE & KATEGORIE ───────────────────────────────────
    _abschnitt('[4] ARTIKEL JE GEMEINDE & KATEGORIE — Beispiele')
    print("  (je Kategorie: bis zu 2 Artikel; nur Gemeinden mit ≥3 Artikeln)")

    for ort, n in reg_zaehler.most_common():
        if n < 3:
            continue
        name = WAPPEN_NAMEN[ort]
        kats_hier = matrix[ort]
        print(f"\n  ┌─ {name.upper()} ({n} Artikel)")
        for kat, arts in sorted(kats_hier.items(), key=lambda x: len(x[1]), reverse=True):
            emoji = KATEGORIE_EMOJI.get(kat, '📰')
            print(f"  │  {emoji} {kat} ({len(arts)})")
            for a in arts[:2]:
                datum  = _datum_kurz(a.get('datum', '') or '')
                quelle = (a.get('quelle') or '').split('.')[0]  # domain ohne TLD
                print(f"  │      → {_titel_kurz(a['titel'], 65)}")
                print(f"  │        {quelle}  {datum}  {a.get('link','')}")
        print(f"  └{'─'*50}")

    # ── [5] MEISTBERICHTETE EREIGNISSE ────────────────────────────────────────
    _abschnitt('[5] MEISTBERICHTETE EREIGNISSE — mehrere Quellen')
    if multi_events:
        for i, ev in enumerate(multi_events, 1):
            print(f"  {i}. {_titel_kurz(ev['titel'])}  [{ev['datum']}]")
            print(f"     {ev['anzahl']} Quellen: {' · '.join(ev['quellen'])}")
    else:
        print("  (keine Ereignisse mit mehreren Quellen)")

    # ── [6] BEVORSTEHENDE VERANSTALTUNGEN ─────────────────────────────────────
    _abschnitt('[6] BEVORSTEHENDE VERANSTALTUNGEN (14-Tage-Fenster)')
    if upcoming:
        seen: set = set()
        for a in upcoming:
            key = a['titel'][:40]
            if key in seen:
                continue
            seen.add(key)
            ort_name = WAPPEN_NAMEN.get(a.get('region') or '', 'Landkreis Fulda')
            datum    = _datum_kurz(a.get('datum', '') or '')
            print(f"  📅 {_titel_kurz(a['titel'])}")
            print(f"     {ort_name}  │  {datum}  │  {a.get('quelle','')}")
    else:
        print("  (keine bevorstehenden Veranstaltungen erkannt)")

    # ── [7] MEISTGEKLICKT (Umami) ─────────────────────────────────────────────
    _abschnitt('[7] MEISTGEKLICKT diese Woche (Umami)')
    if top_klicks:
        for i, tk in enumerate(top_klicks, 1):
            print(f"  {i}. {_titel_kurz(tk['titel'])}  ({tk['klicks']} Klicks)")
    else:
        print("  (kein UMAMI_API_KEY → übersprungen)")

    # ── [8] CANVA / GRAFIK-DATEN ───────────────────────────────────────────────
    _abschnitt('[8] CANVA / GRAFIK-DATEN')
    top_ort_name = WAPPEN_NAMEN.get(reg_zaehler.most_common(1)[0][0], '-') if reg_zaehler else '-'
    print(f"  Hero-Zahl  : {gesamt}")
    print(f"  KW-Badge   : KW {kw}")
    print(f"  Top-Thema  : {kategorien_ranked[0][0] if kategorien_ranked else '-'}")
    print(f"  Top-Ort    : {top_ort_name}  (inkl. Fulda)")
    # Top-Ort ohne Fulda
    ohne_fulda = [(o, n) for o, n in reg_zaehler.most_common() if o not in ('fulda', 'landkreis-fulda')]
    if ohne_fulda:
        print(f"  Top-Ort*   : {WAPPEN_NAMEN[ohne_fulda[0][0]]}  (* excl. Fulda)")

    # ── [9] HASHTAG-BAUSTEINE ─────────────────────────────────────────────────
    _abschnitt('[9] HASHTAG-BAUSTEINE — kopierfertig')
    basis = ["#Fulda", "#LandkreisFulda", "#Osthessen", "#RegioNachrichten",
             "#NachrichtenFulda", "#Lokalnachrichten", "#Hessen"]
    basis_lower = {h.lower() for h in basis}
    print(f"  Basis:  {' '.join(basis)}")
    extra_ort: list[str] = []
    for ort, _ in reg_zaehler.most_common(5):
        if ort in ('landkreis-fulda',):
            continue
        tag = "#" + WAPPEN_NAMEN[ort].replace(" ", "").replace("-", "")
        if tag.lower() not in basis_lower:
            extra_ort.append(tag)
    if extra_ort:
        print(f"  Orte:   {' '.join(extra_ort)}")
    extra_kat: list[str] = []
    for kat, _ in kategorien_ranked[:3]:
        tag = "#" + kat.replace(" ", "").replace("&", "").replace("ä","ae").replace("ü","ue").replace("ö","oe")
        extra_kat.append(tag)
    print(f"  Themen: {' '.join(extra_kat)}")

    print(f"\n{SEP}")


if __name__ == "__main__":
    main()
