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
from collections import defaultdict
from difflib import SequenceMatcher
from html import unescape as html_unescape
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

HTML_QUELLEN = [
    {
        "name": "Fuldaer Zeitung",
        "url": "https://www.fuldaerzeitung.de/fulda/",
        "base_url": "https://www.fuldaerzeitung.de",
        "typ": "Tageszeitung",
        "region": "landkreis-fulda",
        "parser": "fuldaer_zeitung",
    },
    {
        "name": "Osthessen-Zeitung",
        "url": "https://www.osthessen-zeitung.de/lokales/lokales-fd.html",
        "base_url": "https://www.osthessen-zeitung.de",
        "typ": "Online-Portal",
        "region": "osthessen",
        "parser": "osthessen_zeitung",
    },
    {
        "name": "Hochschule Fulda",
        "url": "https://www.hs-fulda.de/unsere-hochschule/alle-meldungen",
        "base_url": "https://www.hs-fulda.de",
        "typ": "Hochschule",
        "region": "landkreis-fulda",
        "parser": "hs_fulda",
    },
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

def _html_fallback_verarbeiten(feed, conn):
    """Führt HTML-Fallback aus, falls RSS eines Feeds fehlschlägt oder leer ist."""
    fb = feed["html_fallback"]
    quelle = {**fb, "name": feed["name"], "typ": feed["typ"], "region": feed["region"]}
    return html_quelle_verarbeiten(quelle, conn)


def feed_verarbeiten(feed, conn):
    print(f"\n{'=' * 55}")
    print(f"Abrufen: {feed['name']}")
    try:
        response = requests.get(feed["rss"], headers=HEADERS, timeout=10)
        parsed = feedparser.parse(response.content)
    except Exception as e:
        print(f"  FEHLER: Verbindung fehlgeschlagen ({e})")
        if feed.get("html_fallback"):
            print(f"  → HTML-Fallback wird verwendet...")
            return _html_fallback_verarbeiten(feed, conn)
        return 0, 0

    echte_eintraege = [e for e in parsed.entries if e.get("title", "").strip()]
    if not echte_eintraege and feed.get("html_fallback"):
        print(f"  RSS liefert keine verwertbaren Einträge → HTML-Fallback wird verwendet...")
        return _html_fallback_verarbeiten(feed, conn)

    neu = 0
    duplikate = 0
    neue_artikel = []
    cursor = conn.cursor()

    for entry in echte_eintraege:
        link         = entry.get("link", "")
        titel        = entry.get("title", "").strip()
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

def html_artikel_holen(url, base_url):
    """Scrapt eine HTML-Listenseite und gibt (titel, link)-Paare zurück."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.raise_for_status()
    except Exception as e:
        print(f"  FEHLER: HTML-Seite nicht erreichbar ({e})")
        return []

    artikel = []
    gesehen_links = set()

    for match in re.finditer(r'<a\s([^>]*class="[^"]*id-LinkOverlay-link[^"]*"[^>]*)>', r.text):
        attrs = match.group(1)
        href_m = re.search(r'href="([^"]+)"', attrs)
        title_m = re.search(r'title="([^"]+)"', attrs)
        if not (href_m and title_m):
            continue
        link = href_m.group(1)
        if link.startswith('//'):
            link = 'https:' + link
        elif link.startswith('/'):
            link = base_url + link
        if not re.search(r'-\d{5,}\.html$', link):
            continue
        if link in gesehen_links:
            continue
        gesehen_links.add(link)
        titel = html_unescape(title_m.group(1)).strip()
        if titel:
            artikel.append((titel, link, None, ""))

    return artikel


def oz_artikel_holen(url, base_url):
    """Scrapt osthessen-zeitung.de (TYPO3/tx_news) und gibt (titel, link, datum, beschreibung)-Tupel zurück."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.raise_for_status()
    except Exception as e:
        print(f"  FEHLER: HTML-Seite nicht erreichbar ({e})")
        return []

    artikel = []
    gesehen_links = set()

    for teil in r.text.split('class="article articletype-0"')[1:]:
        # Anzeigen überspringen
        cat_m = re.search(r'news-list-category[^>]*>\s*([^<]+)', teil)
        if cat_m and cat_m.group(1).strip().lower() == 'anzeige':
            continue

        titel_m = re.search(r'itemprop="headline"[^>]*>([^<]+)', teil)
        link_m  = re.search(r'href="(einzelansicht/news/[^"]+\.html)"', teil)
        if not (titel_m and link_m):
            continue

        link  = base_url + '/' + link_m.group(1)
        if link in gesehen_links:
            continue
        gesehen_links.add(link)

        titel = html_unescape(titel_m.group(1)).strip()

        date_m = re.search(r'<time datetime="(\d{2}\.\d{2}\.\d{4})"', teil)
        try:
            datum = datetime.strptime(date_m.group(1), '%d.%m.%Y').strftime('%Y-%m-%d %H:%M:%S') if date_m else None
        except ValueError:
            datum = None

        teaser_m = re.search(r'itemprop="description"[^>]*>(.*?)</span>', teil, re.DOTALL)
        beschreibung = re.sub(r'<[^>]+>', '', teaser_m.group(1)).strip()[:500] if teaser_m else ""
        beschreibung = html_unescape(beschreibung)

        if titel:
            artikel.append((titel, link, datum, beschreibung))

    return artikel


def hs_fulda_artikel_holen(url, base_url):
    """Scrapt Hochschule Fulda (TYPO3/tx_news) und gibt (titel, link, datum, beschreibung)-Tupel zurück."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.raise_for_status()
    except Exception as e:
        print(f"  FEHLER: HTML-Seite nicht erreichbar ({e})")
        return []

    artikel = []
    gesehen_links = set()

    for teil in r.text.split('class="article')[1:]:
        titel_m = re.search(r'itemprop="headline"[^>]*>([^<]+)', teil)
        if not titel_m:
            continue

        # tx_news wraps the title in an <a> — grab the href closest to the headline
        link_m = re.search(r'href="(/[^"#]+)"[^>]*>\s*(?:<[^>]+>\s*)*<span[^>]+itemprop="headline"', teil, re.DOTALL)
        if not link_m:
            # Fallback: any relative link in the header area of this block
            link_m = re.search(r'href="(/unsere-hochschule/[^"#]+)"', teil)
        if not link_m:
            continue

        link = base_url + link_m.group(1)
        if link in gesehen_links:
            continue
        gesehen_links.add(link)

        titel = html_unescape(titel_m.group(1)).strip()

        # tx_news uses ISO dates: datetime="YYYY-MM-DD"
        date_m = re.search(r'<time[^>]+datetime="(\d{4}-\d{2}-\d{2})"', teil)
        if not date_m:
            # Also handle German format just in case
            date_m = re.search(r'<time datetime="(\d{2}\.\d{2}\.\d{4})"', teil)
            fmt = '%d.%m.%Y'
        else:
            fmt = '%Y-%m-%d'
        try:
            datum = datetime.strptime(date_m.group(1), fmt).strftime('%Y-%m-%d %H:%M:%S') if date_m else None
        except (ValueError, AttributeError):
            datum = None

        teaser_m = re.search(r'itemprop="description"[^>]*>(.*?)</(?:span|div|p)>', teil, re.DOTALL)
        beschreibung = re.sub(r'<[^>]+>', '', teaser_m.group(1)).strip()[:500] if teaser_m else ""
        beschreibung = html_unescape(beschreibung)

        if titel:
            artikel.append((titel, link, datum, beschreibung))

    return artikel


def html_quelle_verarbeiten(quelle, conn):
    print(f"\n{'=' * 55}")
    print(f"Abrufen: {quelle['name']} (HTML)")

    parser = quelle.get("parser", "fuldaer_zeitung")
    if parser == "osthessen_zeitung":
        gefundene = oz_artikel_holen(quelle["url"], quelle["base_url"])
    elif parser == "hs_fulda":
        gefundene = hs_fulda_artikel_holen(quelle["url"], quelle["base_url"])
    else:
        gefundene = html_artikel_holen(quelle["url"], quelle["base_url"])
    if not gefundene:
        print("  Keine Artikel gefunden.")
        return 0, 0

    neu = 0
    duplikate = 0
    neue_artikel = []
    cursor = conn.cursor()
    jetzt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for titel, link, datum, beschreibung in gefundene:
        datum = datum or jetzt
        hash_wert = artikel_hash(link)

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
                quelle["name"], quelle["typ"], quelle["region"],
                datum, jetzt,
                None, beschreibung
            ))
            cursor.execute("RELEASE SAVEPOINT sp1")
            neue_artikel.append((hash_wert, titel))
            neu += 1
        except psycopg2.IntegrityError:
            cursor.execute("ROLLBACK TO SAVEPOINT sp1")
            duplikate += 1

    conn.commit()

    if neue_artikel:
        print(f"  Gefunden: {len(gefundene)} | Neu: {neu} | Duplikate: {duplikate}")
        print(f"  Generiere Tags für {len(neue_artikel)} Artikel...")
        for i in range(0, len(neue_artikel), 20):
            batch = neue_artikel[i:i + 20]
            tags_dict = tags_generieren([t for _, t in batch])
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
        print(f"  Gefunden: {len(gefundene)} | Neu: 0 | Duplikate: {duplikate}")

    cursor.close()
    return neu, duplikate


def _tag_anzahl(tags_str):
    return len([t for t in (tags_str or '').split('·') if t.strip()])

def deduplizieren(conn):
    """
    Zwei Pässe:
    1. Exakte Duplikate (gleicher Titel + gleiche Quelle) → behalte den mit mehr Tags.
    2. Ähnliche Titel (≥ 0.85 Ähnlichkeit) gleicher Quelle → behalte den neueren/reicheren
       (fängt Tippfehler-Korrekturen wie 'Ladesvater' → 'Landesvater' ab).
    """
    cursor = conn.cursor()
    geloescht_gesamt = 0

    # ── Pass 1: Exakte Duplikate (nur unter den 100 neuesten Artikeln) ─────────
    cursor.execute("""
        SELECT titel, quelle
        FROM (SELECT titel, quelle FROM artikel ORDER BY id DESC LIMIT 100) AS neueste
        GROUP BY titel, quelle
        HAVING COUNT(*) > 1
    """)
    gruppen = cursor.fetchall()

    for titel, quelle in gruppen:
        cursor.execute(
            "SELECT id, tags FROM artikel WHERE titel = %s AND quelle = %s ORDER BY id",
            (titel, quelle)
        )
        eintraege = cursor.fetchall()
        beste_id = max(eintraege, key=lambda e: _tag_anzahl(e[1]))[0]
        for id_, _ in eintraege:
            if id_ != beste_id:
                cursor.execute("DELETE FROM artikel WHERE id = %s", (id_,))
                geloescht_gesamt += 1

    conn.commit()
    if gruppen:
        print(f"  Pass 1 (exakt):  {geloescht_gesamt} Duplikat(e) in {len(gruppen)} Gruppe(n) gelöscht")

    # ── Pass 2: Fuzzy-Duplikate (nur unter den 100 neuesten Artikeln) ──────────
    cursor.execute("""
        SELECT id, titel, tags, gespeichert, quelle
        FROM artikel
        ORDER BY id DESC
        LIMIT 100
    """)
    alle = cursor.fetchall()

    nach_quelle = defaultdict(list)
    for row in alle:
        nach_quelle[row[4]].append(row)   # gruppieren nach quelle

    zum_loeschen = set()
    fuzzy_paare = 0

    for quelle, artikel in nach_quelle.items():
        for i, (id_a, titel_a, tags_a, gesp_a, _) in enumerate(artikel):
            if id_a in zum_loeschen:
                continue
            for id_b, titel_b, tags_b, gesp_b, _ in artikel[i + 1:]:
                if id_b in zum_loeschen:
                    continue
                # Nur prüfen wenn Titel nicht identisch (exakter Pass hat das schon erledigt)
                if titel_a == titel_b:
                    continue
                # Mindestlänge von 12 Zeichen verhindert Fehlalarme bei kurzen Titeln
                if len(titel_a) < 12 or len(titel_b) < 12:
                    continue
                aehnlich = SequenceMatcher(None, titel_a.lower(), titel_b.lower()).ratio()
                if aehnlich >= 0.95:
                    fuzzy_paare += 1
                    # Behalte den mit mehr Tags; bei Gleichstand den neueren (höhere id = später gespeichert)
                    if _tag_anzahl(tags_a) >= _tag_anzahl(tags_b):
                        zum_loeschen.add(id_b)
                        print(f"  Fuzzy-Duplikat [{quelle}]: '{titel_b}' → gelöscht (ähnl. {aehnlich:.0%})")
                    else:
                        zum_loeschen.add(id_a)
                        print(f"  Fuzzy-Duplikat [{quelle}]: '{titel_a}' → gelöscht (ähnl. {aehnlich:.0%})")

    for id_ in zum_loeschen:
        cursor.execute("DELETE FROM artikel WHERE id = %s", (id_,))

    conn.commit()
    cursor.close()

    geloescht_gesamt += len(zum_loeschen)
    if zum_loeschen:
        print(f"  Pass 2 (fuzzy):  {len(zum_loeschen)} Artikel in {fuzzy_paare} Paar(en) gelöscht")
    else:
        print("  Pass 2 (fuzzy):  Keine ähnlichen Duplikate gefunden")

    if geloescht_gesamt == 0:
        print("  Deduplizierung:  Datenbank ist sauber")
    return geloescht_gesamt


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

    for quelle in HTML_QUELLEN:
        neu, duplikate = html_quelle_verarbeiten(quelle, conn)
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