import os, json, sys
from urllib.parse import quote
from dotenv import load_dotenv
from pywebpush import webpush, WebPushException
import psycopg2

load_dotenv()

SITE_URL = "https://www.rnfulda.de"
WAPPEN_NAMEN = {
    'fulda': 'Fulda', 'huenfeld': 'Huenfeld', 'hünfeld': 'Hünfeld', 'künzell': 'Künzell',
    'petersberg': 'Petersberg', 'neuhof': 'Neuhof', 'eichenzell': 'Eichenzell',
    'flieden': 'Flieden', 'burghaun': 'Burghaun', 'grossenlueder': 'Grossenlueder', 'großenlüder': 'Grossenlueder',
    'hilders': 'Hilders', 'hofbieber': 'Hofbieber', 'gersfeld': 'Gersfeld',
    'tann': 'Tann', 'eiterfeld': 'Eiterfeld', 'rasdorf': 'Rasdorf',
    'dipperz': 'Dipperz', 'ebersburg': 'Ebersburg', 'ehrenberg': 'Ehrenberg',
    'hosenfeld': 'Hosenfeld', 'kalbach': 'Kalbach', 'nuesttal': 'Nuesttal', 'nüsttal': 'Nuesttal',
    'poppenhausen': 'Poppenhausen', 'bad salzschlirf': 'Bad Salzschlirf',
    'landkreis-fulda': 'Landkreis Fulda',
}

private_key = os.getenv("VAPID_PRIVATE_KEY")
if not private_key:
    print("VAPID_PRIVATE_KEY fehlt in .env")
    sys.exit(1)

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cursor = conn.cursor()

# Find the most recent article whose region matches a known Wappen
cursor.execute("""
    SELECT hash, titel, link, region FROM artikel
    WHERE region = ANY(%s)
    ORDER BY id DESC LIMIT 1
""", (list(WAPPEN_NAMEN.keys()),))
row = cursor.fetchone()

if not row:
    print("Kein passender Artikel gefunden.")
    sys.exit(1)

hash_, titel, link, region = row
wappen_name = WAPPEN_NAMEN[region.lower()]
icon_url = f"{SITE_URL}/Design/Wappen/{quote(wappen_name)}.png"
site_url  = f"{SITE_URL}/?ort={quote(region)}&highlight={hash_}"

print(f"Artikel: {titel}")
print(f"Region:  {region} -> {wappen_name}")
print(f"URL:     {site_url}\n")

payload = json.dumps({
    "title": f"Neues aus {wappen_name}",
    "body":  titel[:120],
    "icon":  icon_url,
    "tag":   hash_,
    "url":   site_url,
})

cursor.execute("SELECT endpoint, p256dh, auth, heimat FROM push_subscriptions")
abonnenten = cursor.fetchall()

if not abonnenten:
    print("Keine Abonnenten in der Datenbank.")
    cursor.close(); conn.close(); sys.exit(0)

print(f"Sende an {len(abonnenten)} Abonnent(en)...")
gesendet, zu_loeschen = 0, []

for endpoint, p256dh, auth, heimat in abonnenten:
    try:
        webpush(
            subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
            data=payload,
            vapid_private_key=private_key,
            vapid_claims={"sub": f"mailto:{os.getenv('VAPID_EMAIL', 'adrian.jestaedt@gmail.com')}"},
        )
        print(f"  OK -> {heimat} ({endpoint[:60]}...)")
        gesendet += 1
    except WebPushException as e:
        status = e.response.status_code if e.response else None
        print(f"  FEHLER {status or 'keine Antwort'} -> {heimat} ({endpoint[:60]}...)")
        # Remove on confirmed permanent failure (410 Gone, 404 Not Found) or no response at all
        if status in (404, 410) or status is None:
            zu_loeschen.append(endpoint)
    except Exception as e:
        print(f"  FEHLER (unbekannt) -> {heimat}: {e}")
        zu_loeschen.append(endpoint)

if zu_loeschen:
    for ep in zu_loeschen:
        cursor.execute("DELETE FROM push_subscriptions WHERE endpoint = %s", (ep,))
    conn.commit()
    print(f"\n  {len(zu_loeschen)} ungueltige Abonnement(s) geloescht.")

cursor.close()
conn.close()
print(f"\nFertig: {gesendet} gesendet, {len(zu_loeschen)} geloescht.")

if gesendet == 0:
    print("\nHinweis: Keine aktiven Abonnements. Bitte auf rnfulda.de die Glocke erneut aktivieren.")
