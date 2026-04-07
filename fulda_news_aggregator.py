"""
Fulda News Aggregator
=====================
Ruft RSS-Feeds ab und speichert Artikel in einer SQLite-Datenbank.

Installation:
    pip install feedparser requests

Ausführen:
    python fulda_news_aggregator.py
"""

import feedparser
import requests
import sqlite3
import hashlib
from datetime import datetime
import zoneinfo
from email.utils import parsedate_to_datetime

# ─────────────────────────────────────────────
# QUELLENLISTE
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
# DATENBANK EINRICHTEN
# ─────────────────────────────────────────────

def datenbank_einrichten(conn):
    """Erstellt die Tabelle falls sie noch nicht existiert."""
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
            gespeichert TEXT
        )
    """)
    conn.commit()
    print(f"Datenbank bereit: {DB_DATEI}")

# ─────────────────────────────────────────────
# HILFSFUNKTIONEN
# ─────────────────────────────────────────────

def artikel_hash(link):
    """Erstellt einen eindeutigen Hash aus der URL – verhindert Duplikate."""
    return hashlib.md5(link.encode()).hexdigest()

def datum_parsen(datum_str):
    """Wandelt RSS-Datum in ein einheitliches Format um."""
    try:
        berlin = zoneinfo.ZoneInfo("Europe/Berlin")
        dt = parsedate_to_datetime(datum_str)
        return dt.astimezone(berlin).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        berlin = zoneinfo.ZoneInfo("Europe/Berlin")
        return datetime.now(berlin).strftime("%Y-%m-%d %H:%M:%S")

# ─────────────────────────────────────────────
# FEED ABRUFEN UND SPEICHERN
# ─────────────────────────────────────────────

def feed_verarbeiten(feed, conn):
    """Ruft einen RSS-Feed ab und speichert neue Artikel in der Datenbank."""
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

    for entry in entries:
        link   = entry.get("link", "")
        titel  = entry.get("title", "Kein Titel")
        datum  = datum_parsen(entry.get("published", ""))
        hash   = artikel_hash(link)

        try:
            conn.execute("""
                INSERT INTO artikel (hash, titel, link, quelle, typ, region, datum, gespeichert)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                hash, titel, link,
                feed["name"], feed["typ"], feed["region"],
                datum,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            neu += 1
        except sqlite3.IntegrityError:
            # Artikel bereits vorhanden (Duplikat)
            duplikate += 1

    conn.commit()
    print(f"  Gefunden: {len(entries)} | Neu: {neu} | Duplikate: {duplikate}")
    return neu, duplikate

# ─────────────────────────────────────────────
# NEUESTE ARTIKEL ANZEIGEN
# ─────────────────────────────────────────────

def neueste_artikel_anzeigen(conn, anzahl=5):
    """Zeigt die neuesten Artikel aus der Datenbank."""
    print(f"\n{'=' * 55}")
    print(f"NEUESTE {anzahl} ARTIKEL IN DER DATENBANK:")
    cursor = conn.execute("""
        SELECT titel, quelle, datum, link
        FROM artikel
        ORDER BY datum DESC
        LIMIT ?
    """, (anzahl,))

    for i, row in enumerate(cursor.fetchall(), 1):
        titel, quelle, datum, link = row
        print(f"\n  [{i}] {titel}")
        print(f"       Quelle: {quelle} | {datum}")
        print(f"       {link}")

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

    # Gesamtanzahl in der Datenbank
    gesamt = conn.execute("SELECT COUNT(*) FROM artikel").fetchone()[0]
    print(f"  Artikel gesamt in DB:     {gesamt}")

    neueste_artikel_anzeigen(conn)

    conn.close()
    print(f"\nFertig! Datenbank gespeichert als: {DB_DATEI}")

if __name__ == "__main__":
    main()