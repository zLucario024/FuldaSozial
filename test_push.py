import os, json, sys
import requests
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

# ── DB ────────────────────────────────────────────────────────────────────────
conn   = psycopg2.connect(os.getenv("DATABASE_URL"))
cursor = conn.cursor()

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
icon_url    = f"{SITE_URL}/Design/Wappen/{quote(wappen_name)}.png"
site_url    = f"{SITE_URL}/?ort={quote(region)}&highlight={hash_}"
title       = f"Neues aus {wappen_name}"
body        = titel[:120]

print(f"Artikel: {titel}")
print(f"Region:  {region} -> {wappen_name}")
print(f"URL:     {site_url}\n")

# ── Web Push ──────────────────────────────────────────────────────────────────
private_key = os.getenv("VAPID_PRIVATE_KEY")
if not private_key:
    print("Web Push: VAPID_PRIVATE_KEY fehlt – wird übersprungen.")
else:
    cursor.execute("SELECT endpoint, p256dh, auth, heimat FROM push_subscriptions")
    abonnenten = cursor.fetchall()
    print(f"Web Push: {len(abonnenten)} Abonnent(en)")

    web_payload  = json.dumps({"title": title, "body": body, "icon": icon_url, "tag": hash_, "url": site_url})
    web_gesendet = 0
    web_loeschen = []

    for endpoint, p256dh, auth, heimat in abonnenten:
        try:
            webpush(
                subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
                data=web_payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": f"mailto:{os.getenv('VAPID_EMAIL', 'adrian.jestaedt@gmail.com')}"},
            )
            print(f"  OK  -> {heimat} ({endpoint[:60]}...)")
            web_gesendet += 1
        except WebPushException as e:
            status = e.response.status_code if e.response else None
            print(f"  ERR {status or '?'} -> {heimat} ({endpoint[:60]}...)")
            if status in (404, 410) or status is None:
                web_loeschen.append(endpoint)
        except Exception as e:
            print(f"  ERR (unbekannt) -> {heimat}: {e}")
            web_loeschen.append(endpoint)

    for ep in web_loeschen:
        cursor.execute("DELETE FROM push_subscriptions WHERE endpoint = %s", (ep,))
    if web_loeschen:
        conn.commit()
    print(f"  => {web_gesendet} gesendet, {len(web_loeschen)} geloescht.\n")

# ── FCM (Android App) ─────────────────────────────────────────────────────────
sa_json    = os.getenv("FIREBASE_SERVICE_ACCOUNT")
project_id = os.getenv("FIREBASE_PROJECT_ID")

if not sa_json or not project_id:
    print("FCM: FIREBASE_SERVICE_ACCOUNT / FIREBASE_PROJECT_ID fehlt – wird übersprungen.")
else:
    import google.auth.transport.requests
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_json),
        scopes=["https://www.googleapis.com/auth/firebase.messaging"],
    )
    creds.refresh(google.auth.transport.requests.Request())
    access_token = creds.token

    cursor.execute("SELECT fcm_token, heimat FROM fcm_subscriptions")
    geraete = cursor.fetchall()
    print(f"FCM:      {len(geraete)} Gerät(e)")

    fcm_gesendet = 0
    fcm_loeschen = []

    for fcm_token, heimat in geraete:
        payload = {
            "message": {
                "token": fcm_token,
                "notification": {"title": title, "body": body},
                "android": {
                    "notification": {
                        "icon": "ic_notification",
                        "color": "#c0152a",
                        "channel_id": "rnfulda_news",
                        "tag": hash_,
                    }
                },
                "data": {"url": site_url, "tag": hash_},
            }
        }
        resp = requests.post(
            f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            print(f"  OK  -> {heimat} ({fcm_token[:40]}...)")
            fcm_gesendet += 1
        else:
            err    = resp.json().get("error", {})
            status = err.get("status", resp.status_code)
            print(f"  ERR {status} -> {heimat} ({fcm_token[:40]}...)")
            if status in ("UNREGISTERED", "INVALID_ARGUMENT"):
                fcm_loeschen.append(fcm_token)

    for tok in fcm_loeschen:
        cursor.execute("DELETE FROM fcm_subscriptions WHERE fcm_token = %s", (tok,))
    if fcm_loeschen:
        conn.commit()
    print(f"  => {fcm_gesendet} gesendet, {len(fcm_loeschen)} geloescht.\n")

cursor.close()
conn.close()
