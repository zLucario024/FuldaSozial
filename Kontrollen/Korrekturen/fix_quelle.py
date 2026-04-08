import sqlite3

conn = sqlite3.connect('fulda_news.db')

# Alle Artikel anzeigen die falsch markiert sind
falsch = conn.execute('''
    SELECT id, titel, quelle 
    FROM artikel 
    WHERE link LIKE "%presseportal%"
    AND quelle != "Presseportal Fulda"
    LIMIT 20
''').fetchall()

print(f"Falsch markierte Artikel: {len(falsch)}")
for id, titel, quelle in falsch:
    print(f"  [{id}] {quelle} → {titel[:50]}")

# Korrigieren
conn.execute('''
    UPDATE artikel 
    SET quelle = "Presseportal Fulda"
    WHERE link LIKE "%presseportal%"
    AND quelle != "Presseportal Fulda"
''')
conn.commit()
print(f"\nKorrigiert: {conn.total_changes} Artikel")
conn.close()