"""
Fulda News Aggregator
=====================
Ruft RSS-Feeds ab, speichert Artikel in PostgreSQL und generiert Tags per KI.
"""

import feedparser
import requests
import psycopg2
import psycopg2.extras
import hashlib
import anthropic
import re
import os
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv

load_dotenv()

FEEDS = [
    {"name": "Hessenschau Osthessen", "url": "https://www.hessenschau.de/osthessen/index.html", "rss": "https://www.hessenschau.de/osthessen/index.rss", "typ": "Öffentlich-rechtlich", "region": "osthessen"},
    {"name": "Hessenschau Alle Hessen", "url": "https://www.hessenschau.de", "rss": "https://www.hessenschau.de/index.rss", "typ": "Öffentlich-rechtlich", "region": "hessen"},
    {"name": "Fuldainfo", "url": "https://www.fuldainfo.de", "rss": "https://www.fuldainfo.de/feed", "typ": "Online-Portal", "region": "landkreis-fulda"},
    {"name": "Landkreis Fulda", "url": "https://www.landkreis-fulda.de", "rss": "https://www.landkreis-fulda.de/rss-feed", "typ": "Öffentlich-rechtlich", "region": "landkreis-fulda"},
    {"name": "Presseportal Fulda", "url": "https://www.presseportal.de/regional/Fulda", "rss": "https://www.presseportal.de/rss/polizei/r/Fulda.rss2", "typ": "Online-Portal", "region": "landkreis-fulda"},
    {"name": "Osthessen-News", "url": "https://osthessen-news.de", "rss": "https://osthessen-news.de/rss_feed.xml", "typ": "Online-Portal", "region": "osthessen"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Quellen, deren RSS-Beschreibung Sidebar-/Infobox-Inhalte enthält → Meta-Tag direkt vom Artikel holen
QUELLEN_META_DESC = {'osthessen-news.de'}

def meta_beschreibung_holen(url):
    """Holt <meta name='description'> direkt aus dem Artikel-HTML."""
    try:
        r = requests.get(url, timeout=8, headers=HEADERS)
        m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', r.text, re.IGNORECASE)
        if not m:
            m = re.search(r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']', r.text, re.IGNORECASE)
        return m.group(1).strip()[:500] if m else ""
    except Exception:
        return ""

def db_verbinden():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def datenbank_einrichten(conn):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS artikel (
            id          SERIAL PRIMARY KEY,
            hash        TEXT UNIQUE,
            titel       TEXT NOT NULL,
            link        TEXT NOT NULL,
            quelle      TEXT,
            typ         TEXT,
            region      TEXT,
            datum       TEXT,
            gespeichert TEXT,
            tags        TEXT,
            beschreibung TEXT
        )
    """)
    conn.commit()
    cursor.close()
    print("Datenbank bereit (PostgreSQL/Supabase)")

def artikel_hash(link):
    return hashlib.md5(link.encode()).hexdigest()

def datum_parsen(datum_str):
    if not datum_str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        dt = parsedate_to_datetime(datum_str)
        dt_berlin = dt.astimezone(timezone(timedelta(hours=2)))
        return dt_berlin.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"  WARNUNG: Datum konnte nicht geparst werden ({datum_str}): {e}")
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def tags_generieren(titel_liste, beschreibung_liste=None):
    if not titel_liste:
        return {}
    if beschreibung_liste is None:
        beschreibung_liste = [""] * len(titel_liste)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {}
    client = anthropic.Anthropic(api_key=api_key)
    titel_text = "\n".join(
        f"{i+1}. {titel}" + (f"\n   Kontext: {beschreibung_liste[i]}" if beschreibung_liste[i] else "")
        for i, titel in enumerate(titel_liste)
    )
    prompt = f"""Du bist ein Redakteur für regionale Nachrichten aus dem Landkreis Fulda in Hessen.
Generiere für jeden Artikel-Titel genau 3-5 kurze deutsche Schlagwörter.
Fokus auf: Ort, Thema, beteiligte Personen oder Institutionen.
Trenne die Tags mit " · ".
Antworte NUR mit den Tags, eine Zeile pro Artikel, keine Nummerierung.

Titel:
{titel_text}"""
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        zeilen = [z.strip() for z in message.content[0].text.strip().split("\n") if z.strip()]
        return {titel: zeilen[i] for i, titel in enumerate(titel_liste) if i < len(zeilen)}
    except Exception as e:
        print(f"  WARNUNG: Tag-Generierung fehlgeschlagen ({e})")
        return {}

def feed_verarbeiten(feed, conn):
    print(f"\n{'=' * 55}")
    print(f"Abrufen: {feed['name']}")
    try:
        response = requests.get(feed["rss"], headers=HEADERS, timeout=10)
        parsed = feedparser.parse(response.content)
    except Exception as e:
        print(f"  FEHLER: Verbindung fehlgeschlagen ({e})")
        return 0, 0

    neu = 0
    duplikate = 0
    neue_artikel = []
    cursor = conn.cursor()

    for entry in parsed.entries:
        link         = entry.get("link", "")
        titel        = entry.get("title", "Kein Titel")
        datum        = datum_parsen(entry.get("published", ""))
        hash_wert    = artikel_hash(link)
        beschreibung = entry.get("summary", "") or entry.get("description", "") or ""
        beschreibung = re.sub(r'<[^>]+>', '', beschreibung).strip()[:500]
        if any(dom in link for dom in QUELLEN_META_DESC):
            meta = meta_beschreibung_holen(link)
            if meta:
                beschreibung = meta

        cursor.execute(
            "SELECT id FROM artikel WHERE titel = %s OR hash = %s",
            (titel, hash_wert)
        )
        if cursor.fetchone():
            duplikate += 1
            continue

        try:
            cursor.execute("SAVEPOINT sp1")
            cursor.execute("""
                INSERT INTO artikel
                (hash, titel, link, quelle, typ, region, datum, gespeichert, tags, beschreibung)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                hash_wert, titel, link,
                feed["name"], feed["typ"], feed["region"],
                datum,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                None,
                beschreibung
            ))
            cursor.execute("RELEASE SAVEPOINT sp1")
            neue_artikel.append((hash_wert, titel))
            neu += 1
        except psycopg2.IntegrityError:
            cursor.execute("ROLLBACK TO SAVEPOINT sp1")
            duplikate += 1

    conn.commit()

    if neue_artikel:
        print(f"  Gefunden: {len(parsed.entries)} | Neu: {neu} | Duplikate: {duplikate}")
        print(f"  Generiere Tags für {len(neue_artikel)} Artikel...")
        for i in range(0, len(neue_artikel), 20):
            batch = neue_artikel[i:i + 20]
            # Beschreibungen aus DB holen
            beschreibungen = []
            for hash_wert, titel in batch:
                cursor.execute("SELECT beschreibung FROM artikel WHERE hash = %s", (hash_wert,))
                row = cursor.fetchone()
                beschreibungen.append(row[0] if row and row[0] else "")
            tags_dict = tags_generieren([t for _, t in batch], beschreibungen)
            for hash_wert, titel in batch:
                tags = tags_dict.get(titel, "")
                if tags:
                    cursor.execute(
                        "UPDATE artikel SET tags = %s WHERE hash = %s",
                        (tags, hash_wert)
                    )
            conn.commit()
            print(f"  Tags generiert: {min(i + 20, len(neue_artikel))}/{len(neue_artikel)}")
    else:
        print(f"  Gefunden: {len(parsed.entries)} | Neu: 0 | Duplikate: {duplikate}")

# Region verfeinern anhand Beschreibung + Tags
    ORTE_LANDKREIS = [
        'fulda', 'hünfeld', 'künzell', 'petersberg', 'neuhof', 'eichenzell',
        'flieden', 'burghaun', 'großenlüder', 'hilders', 'hofbieber', 'gersfeld',
        'tann', 'eiterfeld', 'rasdorf', 'dipperz', 'ebersburg', 'ehrenberg',
        'hosenfeld', 'kalbach', 'nüsttal', 'poppenhausen', 'bad salzschlirf'
    ]

    for hash_wert, titel in neue_artikel:
        cursor.execute(
            "SELECT beschreibung, tags FROM artikel WHERE hash = %s", (hash_wert,)
        )
        row = cursor.fetchone()
        if row:
            text = ((row[0] or '') + ' ' + (row[1] or '') + ' ' + titel).lower()
            if any(ort in text for ort in ORTE_LANDKREIS):
                cursor.execute(
                    "UPDATE artikel SET region = 'landkreis-fulda' WHERE hash = %s",
                    (hash_wert,)
                )
    conn.commit()

    cursor.close()
    return neu, duplikate

def deduplizieren(conn):
    """Findet Artikel mit gleichem Titel + gleicher Quelle und löscht den mit weniger Tags."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT titel, quelle
        FROM artikel
        GROUP BY titel, quelle
        HAVING COUNT(*) > 1
    """)
    gruppen = cursor.fetchall()

    geloescht = 0
    for titel, quelle in gruppen:
        cursor.execute(
            "SELECT id, tags FROM artikel WHERE titel = %s AND quelle = %s ORDER BY id",
            (titel, quelle)
        )
        eintraege = cursor.fetchall()

        def tag_anzahl(e):
            return len([t for t in (e[1] or '').split('·') if t.strip()])

        beste_id = max(eintraege, key=tag_anzahl)[0]
        for id_, _ in eintraege:
            if id_ != beste_id:
                cursor.execute("DELETE FROM artikel WHERE id = %s", (id_,))
                geloescht += 1

    conn.commit()
    cursor.close()
    if geloescht:
        print(f"  Deduplizierung: {geloescht} Duplikat(e) gelöscht ({len(gruppen)} Gruppe(n))")
    else:
        print("  Deduplizierung: Keine Duplikate gefunden")
    return geloescht


def main():
    print("Fulda News Aggregator")
    print(f"Gestartet: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

    conn = db_verbinden()
    datenbank_einrichten(conn)

    gesamt_neu = 0
    gesamt_duplikate = 0

    for feed in FEEDS:
        neu, duplikate = feed_verarbeiten(feed, conn)
        gesamt_neu += neu
        gesamt_duplikate += duplikate

    print(f"\n{'=' * 55}")
    print("DEDUPLIZIERUNG")
    deduplizieren(conn)

    cursor = conn.cursor()
    print(f"\n{'=' * 55}")
    print("ZUSAMMENFASSUNG")
    print(f"  Neue Artikel gespeichert: {gesamt_neu}")
    print(f"  Duplikate übersprungen:   {gesamt_duplikate}")

    cursor.execute("SELECT COUNT(*) FROM artikel")
    gesamt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM artikel WHERE tags IS NOT NULL AND tags != ''")
    mit_tags = cursor.fetchone()[0]
    print(f"  Artikel gesamt in DB:     {gesamt}")
    print(f"  Davon mit Tags:           {mit_tags}")

    print(f"\n{'=' * 55}")
    print("BEISPIEL-ARTIKEL MIT TAGS:")
    cursor.execute("""
        SELECT titel, tags, quelle, datum
        FROM artikel
        WHERE tags IS NOT NULL AND tags != ''
        ORDER BY datum DESC
        LIMIT 3
    """)
    for titel, tags, quelle, datum in cursor.fetchall():
        print(f"\n  {titel}")
        print(f"  Tags: {tags}")
        print(f"  {quelle} | {datum}")

    cursor.close()
    sitemap_generieren(conn)
    conn.close()
    print(f"\nFertig!")


def sitemap_generieren(conn):
    """Regeneriert sitemap.xml mit allen statischen Seiten + allen bekannten Tags aus der DB."""
    from urllib.parse import quote

    cursor = conn.cursor()
    cursor.execute("""
        SELECT tags FROM artikel
        WHERE tags IS NOT NULL AND tags != ''
    """)
    rows = cursor.fetchall()
    cursor.close()

    # Einzelne Tags zählen (getrennt durch " · ")
    from collections import Counter
    tag_counter = Counter()
    for (tags_str,) in rows:
        for tag in tags_str.split('·'):
            tag = tag.strip()
            if tag:
                tag_counter[tag] += 1

    # Nur Tags mit mindestens 3 Artikeln aufnehmen (vermeidet Einzel-Tags)
    haeufige_tags = [tag for tag, count in tag_counter.items() if count >= 3]
    haeufige_tags.sort()

    STATIC_URLS = [
        ("https://fuldasozial.de",                                  "hourly", "1.0"),
        ("https://fuldasozial.de/impressum.html",                   "yearly", "0.3"),
        ("https://fuldasozial.de/datenschutz.html",                 "yearly", "0.3"),
        # ?ort=landkreis-fulda weggelassen — Homepage ist bereits die Landkreis-Ansicht
        ("https://fuldasozial.de/?ort=fulda",                       "hourly", "0.9"),
        ("https://fuldasozial.de/?ort=h%C3%BCnfeld",                "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=k%C3%BCnzell",                "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=petersberg",                  "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=neuhof",                      "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=eichenzell",                  "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=flieden",                     "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=burghaun",                    "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=gro%C3%9Fenl%C3%BCder",       "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=hilders",                     "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=hofbieber",                   "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=gersfeld",                    "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=tann",                        "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=eiterfeld",                   "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=rasdorf",                     "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=dipperz",                     "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=ebersburg",                   "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=ehrenberg",                   "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=hosenfeld",                   "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=kalbach",                     "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=n%C3%BCsttal",                "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=poppenhausen",                "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=bad%20salzschlirf",           "daily",  "0.7"),
        ("https://fuldasozial.de/?ort=hessen",                      "hourly", "0.6"),
        ("https://fuldasozial.de/?kategorie=Lokale%20Vorf%C3%A4lle","hourly", "0.8"),
        ("https://fuldasozial.de/?kategorie=Politik%20%26%20Verwaltung", "daily", "0.7"),
        ("https://fuldasozial.de/?kategorie=Wirtschaft%20%26%20Arbeit",  "daily", "0.7"),
        ("https://fuldasozial.de/?kategorie=Sport",                 "daily",  "0.7"),
        ("https://fuldasozial.de/?kategorie=Kultur%20%26%20Freizeit",    "daily", "0.7"),
        ("https://fuldasozial.de/?kategorie=Bildung%20%26%20Familie",    "daily", "0.7"),
        ("https://fuldasozial.de/?kategorie=Natur%20%26%20Umwelt",       "daily", "0.7"),
        ("https://fuldasozial.de/?kategorie=Verkehr%20%26%20Bau",        "daily", "0.7"),
        ("https://fuldasozial.de/?kategorie=Gesundheit",            "daily",  "0.7"),
    ]

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
             '',
             '  <!-- Statische Seiten & Filter -->']
    for loc, freq, prio in STATIC_URLS:
        lines += [f'  <url>', f'    <loc>{loc}</loc>',
                  f'    <changefreq>{freq}</changefreq>',
                  f'    <priority>{prio}</priority>', f'  </url>']

    lines += ['', f'  <!-- Dynamische Tag-Seiten ({len(haeufige_tags)} Tags mit ≥3 Artikeln) -->']
    for tag in haeufige_tags:
        encoded = quote(tag, safe='')
        lines += [f'  <url>',
                  f'    <loc>https://fuldasozial.de/?tag={encoded}</loc>',
                  f'    <changefreq>daily</changefreq>',
                  f'    <priority>0.5</priority>',
                  f'  </url>']

    lines += ['', '</urlset>', '']

    sitemap_pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sitemap.xml')
    with open(sitemap_pfad, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"  Sitemap aktualisiert: {len(STATIC_URLS)} statische + {len(haeufige_tags)} Tag-URLs → sitemap.xml")

if __name__ == "__main__":
    main()