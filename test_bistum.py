import requests
import feedparser

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

url = "https://www.bistum-fulda.de/bistum_fulda/presse_medien/wRss/"

response = requests.get(url, headers=headers, timeout=10)
parsed = feedparser.parse(response.content)
print(f"Status: {response.status_code}")
print(f"Artikel gefunden: {len(parsed.entries)}")

if parsed.entries:
    for entry in parsed.entries[:3]:
        print(f"  - {entry.get('title', 'kein Titel')}")