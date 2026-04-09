import sqlite3
import psycopg2

SUPABASE_URL = "postgresql://postgres.thfhjdijwpwdbxznsvhe:-8sYGkqhq?bhStG@aws-1-eu-central-1.pooler.supabase.com:6543/postgres"

sqlite_conn = sqlite3.connect('fulda_news.db')
pg_conn = psycopg2.connect(SUPABASE_URL)
pg_cursor = pg_conn.cursor()

artikel = sqlite_conn.execute('''
    SELECT hash, titel, link, quelle, typ, region, 
           datum, gespeichert, tags, beschreibung 
    FROM artikel
''').fetchall()

print(f"Migriere {len(artikel)} Artikel...")

for a in artikel:
    try:
        pg_cursor.execute('''
            INSERT INTO artikel 
            (hash, titel, link, quelle, typ, region, datum, gespeichert, tags, beschreibung)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hash) DO NOTHING
        ''', a)
    except Exception as e:
        print(f"Fehler: {e}")

pg_conn.commit()
print("Migration abgeschlossen!")

count = pg_cursor.execute("SELECT COUNT(*) FROM artikel").fetchone()[0]
print(f"Artikel in Supabase: {count}")

pg_cursor.close()
pg_conn.close()
sqlite_conn.close()