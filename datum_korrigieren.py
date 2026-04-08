import sqlite3
import requests
import feedparser
from email.utils import parsedate_to_datetime
from datetime import timezone, timedelta

FEEDS = [
    "https://www.hessenschau.de/osthessen/index.rss",
    "https://www.hessenschau.de/index.rss",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

utc_offset = timedelta(hours=2)
berlin = timezone(utc_offset)

conn = sqlite3.connect('fulda_news.db')
korrigiert = 0

for rss_url in FEEDS:
    response = requests.get(rss_url, headers=HEADERS, timeout=10)
    parsed = feedparser.parse(response.content)
    
    for entry in parsed.entries:
        link = entry.get('link', '')
        published = entry.get('published', '')
        if not published:
            continue
        try:
            dt = parsedate_to_datetime(published)
            datum = dt.astimezone(berlin).strftime("%Y-%m-%d %H:%M:%S")
            result = conn.execute(
                "UPDATE artikel SET datum = ? WHERE link = ? AND datum = gespeichert",
                (datum, link)
            )
            if result.rowcount > 0:
                korrigiert += result.rowcount
        except Exception as e:
            print(f"Fehler: {e}")

conn.commit()
print(f"Korrigiert: {korrigiert} Artikel")
conn.close()