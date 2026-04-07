"""
Fulda News Aggregator
=====================
Ruft RSS-Feeds ab, speichert Artikel in SQLite und generiert Tags per KI.

Installation:
    pip install feedparser requests anthropic python-dotenv

Ausführen:
    python fulda_news_aggregator.py
"""

import feedparser
import requests
import sqlite3
import hashlib
import anthropic
from datetime import datetime
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv
import os

load_dotenv()

# ─────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────

FEEDS = [
    {
        "name": "Hessenschau Osthessen",
        "url": "https://www.hessenschau.de/osthessen/index.html",
        "rss": "https://www.hessenschau.de/osthessen/index.rss",
        "typ": "Öffentlich-rechtlich",
        "region": "landkreis-fulda"
    },
    {
        "name": "Hessenschau Alle Hessen",
        "url": "https://www.hessenschau.de",
        "rss": "https://www.hessenschau.de/index.rss",
        "typ": "Öffentlich-rechtlich",
        "region": "hessen"
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

DB_DATEI = "fulda_news.db"

# ─────────────────────────────────────────────
# DATENBANK
# ─────────────────────────────────────────────

def datenbank_einrichten(conn):
    """Erstellt die Tabelle und fügt tags-Spalte hinzu falls nötig."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS artikel (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            hash        TEXT UNIQUE,
            titel       TEXT NOT NULL,
            link        TEXT NOT NULL,
            quelle      TEXT,
            typ         TEXT,
            region      TEXT,
            datum       TEXT,
            gespeichert TEXT,
            tags        TEXT
        )
    """)
    # Tags-Spalte nachrüsten falls Datenbank bereits existiert
    try:
        conn.execute("ALTER TABLE artikel ADD COLUMN tags TEXT")
    except sqlite3.OperationalError:
        pass  # Spalte existiert bereits
    conn.commit()
    print(f"Datenbank bereit: {DB_DATEI}")

# ─────────────────────────────────────────────
# HILFSFUNKTIONEN
# ─────────────────────────────────────────────

def artikel_hash(link):
    return hashlib.md5(link.encode()).hexdigest()

def datum_parsen(datum_str):
    try:
        import zoneinfo
        berlin = zoneinfo.ZoneInfo("Europe/Berlin")
        dt = parsedate_to_datetime(datum_str)
        return dt.astimezone(berlin).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ─────────────────────────────────────────────
# KI TAG-GENERIERUNG
# ─────────────────────────────────────────────

def tags_generieren(titel_liste):
    """
    Schickt eine Liste von Titeln an Claude Haiku.
    Gibt ein Dictionary {titel: "tag1 · tag2 · tag3"} zurück.
    """
    if not titel_liste:
        return {}

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  WARNUNG: Kein API-Schlüssel gefunden, Tags werden übersprungen.")
        return {}

    client = anthropic.Anthropic(api_key=api_key)

    titel_text = "\n".join(
        f"{i+1}. {titel}" for i, titel in enumerate(titel_liste)
    )

    prompt = f"""Du bist ein Redakteur für regionale Nachrichten aus Hessen.
Generiere für jeden Artikel-Titel genau 3-5 kurze deutsche Schlagwörter.
Fokus auf: Ort, Thema, beteiligte Personen oder Institutionen.
Trenne die Tags mit " · ".
Antworte NUR mit den Tags, eine Zeile pro Artikel, keine Nummerierung.

Titel:
{titel_text}"""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        zeilen = message.content[0].text.strip().split("\n")
        ergebnis = {}
        for i, titel in enumerate(titel_liste):
            if i < len(zeilen):
                ergebnis[titel] = zeilen[i].strip()
        return ergebnis
    except Exception as e:
        print(f"  WARNUNG: Tag-Generierung fehlgeschlagen ({e})")
        return {}

# ─────────────────────────────────────────────
# FEED VERARBEITEN
# ─────────────────────────────────────────────

def feed_verarbeiten(feed, conn):
    print(f"\n{'=' * 55}")
    print(f"Abrufen: {feed['name']}")

    try:
        response = requests.get(feed["rss"], headers=HEADERS, timeout=10)
        parsed = feedparser.parse(response.content)
    except Exception as e:
        print(f"  FEHLER: Verbindung fehlgeschlagen ({e})")
        return 0, 0

    entries = parsed.entries
    neu = 0
    duplikate = 0
    neue_artikel = []

    # Erst alle neuen Artikel speichern (ohne Tags)
    for entry in entries:
        link  = entry.get("link", "")
        titel = entry.get("title", "Kein Titel")
        datum = datum_parsen(entry.get("published", ""))
        hash  = artikel_hash(link)

        try:
            conn.execute("""
                INSERT INTO artikel
                (hash, titel, link, quelle, typ, region, datum, gespeichert, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                hash, titel, link,
                feed["name"], feed["typ"], feed["region"],
                datum,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                None
            ))
            neue_artikel.append((hash, titel))
            neu += 1
        except sqlite3.IntegrityError:
            duplikate += 1

    conn.commit()

    # Tags für neue Artikel generieren (in Batches à 20)
    if neue_artikel:
        print(f"  Gefunden: {len(entries)} | Neu: {neu} | Duplikate: {duplikate}")
        print(f"  Generiere Tags für {len(neue_artikel)} Artikel...")

        batch_groesse = 20
        for i in range(0, len(neue_artikel), batch_groesse):
            batch = neue_artikel[i:i + batch_groesse]
            titel_liste = [t for _, t in batch]
            tags_dict = tags_generieren(titel_liste)

            for hash_wert, titel in batch:
                tags = tags_dict.get(titel, "")
                if tags:
                    conn.execute(
                        "UPDATE artikel SET tags = ? WHERE hash = ?",
                        (tags, hash_wert)
                    )
            conn.commit()
            print(f"  Tags generiert: {min(i + batch_groesse, len(neue_artikel))}/{len(neue_artikel)}")
    else:
        print(f"  Gefunden: {len(entries)} | Neu: 0 | Duplikate: {duplikate}")

    return neu, duplikate

# ─────────────────────────────────────────────
# HAUPTPROGRAMM
# ─────────────────────────────────────────────

def main():
    print("Fulda News Aggregator")
    print(f"Gestartet: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

    conn = sqlite3.connect(DB_DATEI)
    datenbank_einrichten(conn)

    gesamt_neu = 0
    gesamt_duplikate = 0

    for feed in FEEDS:
        neu, duplikate = feed_verarbeiten(feed, conn)
        gesamt_neu += neu
        gesamt_duplikate += duplikate

    print(f"\n{'=' * 55}")
    print("ZUSAMMENFASSUNG")
    print(f"  Neue Artikel gespeichert: {gesamt_neu}")
    print(f"  Duplikate übersprungen:   {gesamt_duplikate}")

    gesamt = conn.execute("SELECT COUNT(*) FROM artikel").fetchone()[0]
    mit_tags = conn.execute(
        "SELECT COUNT(*) FROM artikel WHERE tags IS NOT NULL AND tags != ''"
    ).fetchone()[0]
    print(f"  Artikel gesamt in DB:     {gesamt}")
    print(f"  Davon mit Tags:           {mit_tags}")

    # Beispiel: 3 Artikel mit Tags anzeigen
    print(f"\n{'=' * 55}")
    print("BEISPIEL-ARTIKEL MIT TAGS:")
    rows = conn.execute("""
        SELECT titel, tags, quelle, datum
        FROM artikel
        WHERE tags IS NOT NULL AND tags != ''
        ORDER BY datum DESC
        LIMIT 3
    """).fetchall()

    for titel, tags, quelle, datum in rows:
        print(f"\n  {titel}")
        print(f"  Tags: {tags}")
        print(f"  {quelle} | {datum}")

    conn.close()
    print(f"\nFertig!")

if __name__ == "__main__":
    main()