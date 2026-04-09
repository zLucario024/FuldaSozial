import sqlite3

conn = sqlite3.connect('fulda_news.db')

# Prüfen ob Spalte existiert
spalten = [row[1] for row in conn.execute("PRAGMA table_info(artikel)").fetchall()]
print(f"Spalten in der Tabelle: {', '.join(spalten)}")
print(f"Beschreibung vorhanden: {'beschreibung' in spalten}")

# Artikel mit Beschreibung anzeigen
mit = conn.execute("SELECT COUNT(*) FROM artikel WHERE beschreibung IS NOT NULL AND beschreibung != ''").fetchone()[0]
ohne = conn.execute("SELECT COUNT(*) FROM artikel WHERE beschreibung IS NULL OR beschreibung = ''").fetchone()[0]
print(f"\nArtikel mit Beschreibung:    {mit}")
print(f"Artikel ohne Beschreibung:   {ohne}")

# Beispiel anzeigen
beispiel = conn.execute("""
    SELECT titel, beschreibung 
    FROM artikel 
    WHERE beschreibung IS NOT NULL AND beschreibung != ''
    LIMIT 2
""").fetchall()

if beispiel:
    print("\nBeispiele:")
    for titel, beschreibung in beispiel:
        print(f"\n  Titel: {titel[:60]}")
        print(f"  Beschreibung: {beschreibung[:150]}...")
else:
    print("\nNoch keine Beschreibungen gespeichert – Aggregator nochmal ausführen!")

conn.close()