import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM artikel WHERE tags IS NULL OR tags = ''")
n = cursor.fetchone()[0]
print(f"Artikel ohne Tags: {n}")
cursor.close()
conn.close()
