import sqlite3
conn = sqlite3.connect('fulda_news.db')
rows = conn.execute('''
    SELECT titel, datum, gespeichert
    FROM artikel
    ORDER BY id DESC
    LIMIT 6
''').fetchall()
for titel, datum, gespeichert in rows:
    print(f'{titel[:50]}')
    print(f'  datum:       {datum}')
    print(f'  gespeichert: {gespeichert}')
    print()
conn.close()