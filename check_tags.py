import sqlite3
conn = sqlite3.connect('fulda_news.db')
n = conn.execute('SELECT COUNT(*) FROM artikel WHERE tags IS NULL OR tags = ""').fetchone()[0]
print(f'Artikel ohne Tags: {n}')
conn.close()