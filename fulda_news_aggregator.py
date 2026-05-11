"""
Fulda News Aggregator
=====================
Ruft RSS-Feeds ab, speichert Artikel in PostgreSQL und generiert Tags per KI.
"""

import feedparser
import requests
import psycopg2
import psycopg2.extras
import hashlib
import anthropic
import re
import os
import json
from urllib.parse import quote
from collections import defaultdict
from difflib import SequenceMatcher
from html import unescape as html_unescape
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from pywebpush import webpush, WebPushException

load_dotenv()

SITE_URL = "https://www.rnfulda.de"

WAPPEN_NAMEN = {
    'fulda': 'Fulda', 'hünfeld': 'Hünfeld', 'künzell': 'Künzell',
    'petersberg': 'Petersberg', 'neuhof': 'Neuhof', 'eichenzell': 'Eichenzell',
    'flieden': 'Flieden', 'burghaun': 'Burghaun', 'großenlüder': 'Großenlüder',
    'hilders': 'Hilders', 'hofbieber': 'Hofbieber', 'gersfeld': 'Gersfeld',
    'tann': 'Tann', 'eiterfeld': 'Eiterfeld', 'rasdorf': 'Rasdorf',
    'dipperz': 'Dipperz', 'ebersburg': 'Ebersburg', 'ehrenberg': 'Ehrenberg',
    'hosenfeld': 'Hosenfeld', 'kalbach': 'Kalbach', 'nüsttal': 'Nüsttal',
    'poppenhausen': 'Poppenhausen', 'bad salzschlirf': 'Bad Salzschlirf',
    'landkreis-fulda': 'Landkreis Fulda',
}

# Hessian cities/districts outside Landkreis Fulda.
# If an article tagged with one of these has region='landkreis-fulda', demote to 'hessen'.
_HESSISCHE_FREMDE = frozenset({
    'frankfurt', 'frankfurt am main', 'wiesbaden', 'kassel', 'darmstadt',
    'gießen', 'offenbach', 'hanau', 'marburg', 'limburg', 'bad homburg',
    'rüsselsheim', 'friedberg', 'bad nauheim', 'langen', 'dreieich',
    'bensheim', 'heppenheim', 'michelstadt', 'erbach', 'viernheim',
    'langenselbold', 'vogelsbergkreis', 'vogelsberg', 'main-kinzig-kreis', 'main-kinzig',
    'hersfeld-rotenburg', 'bad hersfeld', 'rotenburg an der fulda',
    'lahn-dill-kreis', 'lahn-dill', 'wetteraukreis', 'wetterau',
    'odenwaldkreis', 'odenwald', 'rheingau-taunus-kreis', 'rheingau',
    'hochtaunuskreis', 'hochtaunus', 'groß-gerau', 'darmstadt-dieburg',
    'bergstraße', 'waldeck-frankenberg', 'schwalm-eder-kreis', 'schwalm-eder',
    'werra-meißner-kreis', 'werra-meißner', 'kassel-land', 'fulda-oda', 'nordhessen'
})

# Cities and regions clearly outside Hessen.
# Articles from landkreis-fulda feeds tagged with these get demoted to 'bundesweit'.
_BUNDESWEITE_ORTE = frozenset({
    'berlin', 'hamburg', 'münchen', 'köln', 'stuttgart', 'düsseldorf',
    'leipzig', 'dresden', 'hannover', 'bremen', 'nürnberg', 'dortmund',
    'essen', 'bochum', 'wuppertal', 'bielefeld', 'bonn', 'mannheim',
    'karlsruhe', 'augsburg', 'münster', 'aachen', 'freiburg', 'kiel',
    'lübeck', 'erfurt', 'rostock', 'mainz', 'saarbrücken', 'potsdam',
    'magdeburg', 'schwerin', 'chemnitz', 'halle', 'duisburg', 'gelsenkirchen',
    'niedersachsen', 'nordrhein-westfalen', 'nrw', 'rheinland-pfalz',
    'sachsen', 'thüringen', 'sachsen-anhalt', 'mecklenburg-vorpommern',
    'schleswig-holstein', 'saarland', 'brandenburg', 'bayern',
    'baden-württemberg', 'bundesregierung', 'bundestag', 'bundesrat',
})

KATEGORIE_EMOJI = {
    'Vorfälle':             '🚨',
    'Politik & Verwaltung': '🏛️',
    'Wirtschaft & Arbeit':  '💼',
    'Sport':                '⚽',
    'Kultur & Freizeit':    '🎭',
    'Bildung & Familie':    '📚',
    'Natur & Umwelt':       '🌿',
    'Verkehr & Bau':        '🚧',
    'Gesundheit':           '🏥',
    'Sonstiges':            '📰',
}

_KATEGORIE_SCHLUESSEL = {
    'Vorfälle':             ['unfall','vorfall','brand','blaulicht','mord','betrug','einbruch','polizei','feuer','rettung','diebstahl','gewalt','verletzt','notfall','einsatz','vermisst','todesfall'],
    'Politik & Verwaltung': ['politik','verwaltung','bundestag','partei','minister','kanzler','koalition','bürgermeister','gemeinde','stadtrat','landrat','wahl'],
    'Wirtschaft & Arbeit':  ['wirtschaft','insolvenz','unternehmen','konjunktur','inflation','streik','arbeitslos','stellenanzeige','eröffnung'],
    'Sport':                ['sport','fußball','handball','liga','meisterschaft','turnier','leichtathletik','basketball','eishockey'],
    'Kultur & Freizeit':    ['kultur','konzert','festival','ausstellung','theater','museum','kunst','flohmarkt','literatur','fest','event'],
    'Bildung & Familie':    ['bildung','schule','kita','studium','universität','abitur','ausbildung','hochschule','jugend','kinder','familie'],
    'Natur & Umwelt':       ['natur','umwelt','klima','naturschutz','hochwasser','überschwemmung','wetter','wald'],
    'Verkehr & Bau':        ['verkehr','baustelle','sperrung','autobahn','öpnv','stau','straße','bus','bahn','brücke','umleitung'],
    'Gesundheit':           ['gesundheit','krankenhaus','klinik','medizin','arzt','klinikum','pflege','impfung','patient'],
}


def kategorie_bestimmen(titel, tags):
    text = f"{titel or ''} {tags or ''}".lower()
    for kat, schluessel in _KATEGORIE_SCHLUESSEL.items():
        if any(s in text for s in schluessel):
            return kat
    return 'Sonstiges'


def _fcm_access_token():
    """Get a short-lived OAuth2 bearer token for the FCM HTTP v1 API."""
    import google.auth.transport.requests
    from google.oauth2 import service_account
    sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if not sa_json:
        return None
    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_json),
        scopes=["https://www.googleapis.com/auth/firebase.messaging"],
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _fcm_senden(token, title, body, url, tag, icon_url=""):
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    access_token = _fcm_access_token()
    if not access_token or not project_id:
        return None
    payload = {
        "message": {
            "token": token,
            "android": {"priority": "high"},
            "data": {
                "title": title,
                "body": body,
                "url": url,
                "tag": tag,
                "icon_url": icon_url,
            },
        }
    }
    return requests.post(
        f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )


def benachrichtigungen_senden(conn, cutoff_iso):
    """Subscriber-centric push: for each unique Heimat in the subscription tables,
    find the most recent new article mentioning that place (region, tags, or title),
    then send one notification to all subscribers with that Heimat."""
    private_key = os.getenv("VAPID_PRIVATE_KEY")
    cursor = conn.cursor()

    # Collect all unique heimat values that are in WAPPEN_NAMEN
    cursor.execute("""
        SELECT heimat FROM push_subscriptions
        UNION
        SELECT heimat FROM fcm_subscriptions
    """)
    alle_heimaten = [r[0] for r in cursor.fetchall() if r[0] and r[0] in WAPPEN_NAMEN]

    if not alle_heimaten:
        print("  Keine Abonnenten mit bekanntem Heimat-Ort vorhanden.")
        cursor.close()
        return

    web_gesendet = web_fehler = fcm_gesendet = fcm_fehler = 0
    web_loeschen = []
    fcm_loeschen = []

    # Load already-sent hashes so we don't repeat notifications
    cursor.execute("SELECT heimat, artikel_hash FROM push_benachrichtigt")
    bereits_gesendet = {r[0]: r[1] for r in cursor.fetchall()}

    for heimat in alle_heimaten:
        # All new articles that mention this Heimat in region, tags or title
        cursor.execute("""
            SELECT hash, titel, link, region, tags FROM artikel
            WHERE gespeichert >= %s
              AND (
                region = %s
                OR LOWER(tags)  LIKE %s
                OR LOWER(titel) LIKE %s
              )
            ORDER BY id DESC
        """, (cutoff_iso, heimat, f'%{heimat}%', f'%{heimat}%'))
        rows = cursor.fetchall()
        if not rows:
            continue

        hash_, titel, link, region, tags = rows[0]
        anzahl = len(rows)

        # Skip if this exact article was already notified for this heimat
        if bereits_gesendet.get(heimat) == hash_:
            continue

        kat = kategorie_bestimmen(titel, tags)
        emoji = KATEGORIE_EMOJI.get(kat, '📰')
        wappen_name = WAPPEN_NAMEN[heimat]
        icon_url = f"{SITE_URL}/Design/Wappen/{quote(wappen_name)}.png"
        site_url = f"{SITE_URL}/?ort={quote(heimat)}&highlight={hash_}"
        title_text = f"{emoji} Neues aus {wappen_name}"
        if anzahl > 1:
            body = f"{titel[:80]} – und {anzahl - 1} weitere"
        else:
            body = titel[:120]

        print(f"  [{heimat}] {anzahl} Artikel · '{titel[:55]}…'")

        # --- Web Push ---
        if private_key:
            web_payload = json.dumps({
                "title": title_text, "body": body, "icon": icon_url,
                "tag": hash_, "url": site_url,
            })
            cursor.execute(
                "SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE heimat = %s",
                (heimat,)
            )
            for endpoint, p256dh, auth in cursor.fetchall():
                try:
                    webpush(
                        subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
                        data=web_payload,
                        vapid_private_key=private_key,
                        vapid_claims={"sub": f"mailto:{os.getenv('VAPID_EMAIL', 'adrian.jestaedt@gmail.com')}"},
                    )
                    web_gesendet += 1
                except WebPushException as e:
                    status = e.response.status_code if e.response else None
                    if status in (404, 410) or status is None:
                        web_loeschen.append(endpoint)
                    web_fehler += 1
                except Exception:
                    web_loeschen.append(endpoint)
                    web_fehler += 1

        # --- FCM (Android) ---
        cursor.execute(
            "SELECT fcm_token FROM fcm_subscriptions WHERE heimat = %s",
            (heimat,)
        )
        for (fcm_token,) in cursor.fetchall():
            try:
                resp = _fcm_senden(fcm_token, title_text, body, site_url, hash_, icon_url)
                if resp is None:
                    break  # FCM not configured
                if resp.status_code == 200:
                    fcm_gesendet += 1
                else:
                    err = resp.json().get("error", {})
                    if err.get("status") in ("UNREGISTERED", "INVALID_ARGUMENT"):
                        fcm_loeschen.append(fcm_token)
                    fcm_fehler += 1
            except Exception:
                fcm_fehler += 1

        # Record this article as sent so the next run won't repeat it
        cursor.execute("""
            INSERT INTO push_benachrichtigt (heimat, artikel_hash, gesendet_am)
            VALUES (%s, %s, %s)
            ON CONFLICT (heimat) DO UPDATE
              SET artikel_hash = EXCLUDED.artikel_hash,
                  gesendet_am  = EXCLUDED.gesendet_am
        """, (heimat, hash_, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()

    for ep in web_loeschen:
        cursor.execute("DELETE FROM push_subscriptions WHERE endpoint = %s", (ep,))
    for tok in fcm_loeschen:
        cursor.execute("DELETE FROM fcm_subscriptions WHERE fcm_token = %s", (tok,))
    if web_loeschen or fcm_loeschen:
        conn.commit()

    cursor.close()
    print(f"  Web Push: {web_gesendet} gesendet, {web_fehler} Fehler, {len(web_loeschen)} abgelaufen")
    print(f"  FCM:      {fcm_gesendet} gesendet, {fcm_fehler} Fehler, {len(fcm_loeschen)} abgelaufen")


FEEDS = [
    {"name": "Hessenschau Osthessen", "url": "https://www.hessenschau.de/osthessen/index.html", "rss": "https://www.hessenschau.de/osthessen/index.rss", "typ": "Öffentlich-rechtlich", "region": "osthessen"},
    {"name": "Hessenschau Alle Hessen", "url": "https://www.hessenschau.de", "rss": "https://www.hessenschau.de/index.rss", "typ": "Öffentlich-rechtlich", "region": "hessen"},
    {"name": "Fuldainfo", "url": "https://www.fuldainfo.de", "rss": "https://www.fuldainfo.de/feed", "typ": "Online-Portal", "region": "landkreis-fulda"},
    {"name": "Landkreis Fulda", "url": "https://www.landkreis-fulda.de", "rss": "https://www.landkreis-fulda.de/rss-feed", "typ": "Öffentlich-rechtlich", "region": "landkreis-fulda"},
    {"name": "Presseportal Fulda", "url": "https://www.presseportal.de/regional/Fulda", "rss": "https://www.presseportal.de/rss/polizei/r/Fulda.rss2", "typ": "Online-Portal", "region": "landkreis-fulda"},
    {"name": "Osthessen-News", "url": "https://osthessen-news.de", "rss": "https://osthessen-news.de/rss_feed.xml", "typ": "Online-Portal", "region": "osthessen"},
    {"name": "Marktkorb", "url": "https://www.marktkorb.de", "rss": "https://www.marktkorb.de/feed/", "typ": "Wochenblatt", "region": "landkreis-fulda"},
]

HTML_QUELLEN = [
    {
        "name": "Fuldaer Zeitung",
        "url": "https://www.fuldaerzeitung.de/fulda/",
        "base_url": "https://www.fuldaerzeitung.de",
        "typ": "Tageszeitung",
        "region": "landkreis-fulda",
        "parser": "fuldaer_zeitung",
    },
    {
        "name": "Osthessen-Zeitung",
        "url": "https://www.osthessen-zeitung.de/lokales/lokales-fd.html",
        "base_url": "https://www.osthessen-zeitung.de",
        "typ": "Online-Portal",
        "region": "osthessen",
        "parser": "osthessen_zeitung",
    },
    {
        "name": "Hochschule Fulda",
        "url": "https://www.hs-fulda.de/unsere-hochschule/alle-meldungen",
        "base_url": "https://www.hs-fulda.de",
        "typ": "Hochschule",
        "region": "landkreis-fulda",
        "parser": "hs_fulda",
    },
    {
        "name": "GemeindeZeitung Petersberg",
        "url": "https://ol.wittich.de/titel/1142",
        "base_url": "https://ol.wittich.de",
        "typ": "Amtsblatt",
        "region": "petersberg",
        "parser": "wittich",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

# ── Kategorie-Keywords (single source of truth: kategorien.json) ──
def _lade_kategorie_keywords():
    pfad = os.path.join(os.path.dirname(__file__), 'kategorien.json')
    try:
        with open(pfad, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

_KATEGORIE_KEYWORDS = _lade_kategorie_keywords()

def _kategorie_hinweis():
    """Compact category → keyword mapping for the AI tagging prompt."""
    lines = []
    for name, data in _KATEGORIE_KEYWORDS.items():
        if name == 'Sonstiges':
            continue
        wichtig = (data.get('lock') or []) + (data.get('strong') or [])
        extra   = [k for k in (data.get('keys') or []) if k not in wichtig][:10]
        alle    = wichtig + extra
        if alle:
            lines.append(f"  {name}: {', '.join(alle)}")
    return '\n'.join(lines)

HTML_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1",
}


def html_session_erstellen():
    """Erstellt eine requests.Session, die beim ersten Aufruf die Startseite besucht,
    um Cookies (z.B. Cloudflare-Consent) zu setzen – genau wie ein echter Browser."""
    session = requests.Session()
    session.headers.update(HTML_HEADERS)
    return session

# Quellen, deren RSS-Beschreibung Sidebar-/Infobox-Inhalte enthält ODER leer ist →
# Meta-Tag direkt vom Artikel holen, um der KI mehr Kontext zu geben.
QUELLEN_META_DESC = {'osthessen-news.de', 'fuldaerzeitung.de'}

def auf_zwei_saetze(text: str) -> str:
    """Kürzt Text auf maximal zwei Sätze."""
    if not text:
        return text
    saetze = re.split(r'(?<=[.!?])\s+', text.strip())
    return ' '.join(saetze[:2])

def meta_beschreibung_holen(url):
    """Holt <meta name='description'> direkt aus dem Artikel-HTML."""
    try:
        r = requests.get(url, timeout=8, headers=HEADERS)
        m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', r.text, re.IGNORECASE)
        if not m:
            m = re.search(r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']', r.text, re.IGNORECASE)
        return auf_zwei_saetze(m.group(1).strip()) if m else ""
    except Exception:
        return ""

def db_verbinden():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def datenbank_einrichten(conn):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS artikel (
            id          SERIAL PRIMARY KEY,
            hash        TEXT UNIQUE,
            titel       TEXT NOT NULL,
            link        TEXT NOT NULL,
            quelle      TEXT,
            typ         TEXT,
            region      TEXT,
            datum       TEXT,
            gespeichert TEXT,
            tags        TEXT,
            beschreibung TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_datum ON artikel(datum)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_quelle_region ON artikel(quelle, region)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_region ON artikel(region)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS push_benachrichtigt (
            heimat      TEXT PRIMARY KEY,
            artikel_hash TEXT NOT NULL,
            gesendet_am TEXT NOT NULL
        )
    """)
    conn.commit()
    cursor.close()
    print("Datenbank bereit (PostgreSQL/Supabase)")

def artikel_hash(link):
    return hashlib.md5(link.encode()).hexdigest()

def datum_parsen(datum_str):
    if not datum_str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        dt = parsedate_to_datetime(datum_str)
        try:
            dt_local = dt.astimezone(ZoneInfo("Europe/Berlin"))
        except Exception:
            dt_local = dt.astimezone(timezone(timedelta(hours=2)))
        return dt_local.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"  WARNUNG: Datum konnte nicht geparst werden ({datum_str}): {e}")
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def tags_generieren(titel_liste, beschreibung_liste=None):
    if not titel_liste:
        return {}
    if beschreibung_liste is None:
        beschreibung_liste = [""] * len(titel_liste)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {}
    client = anthropic.Anthropic(api_key=api_key)
    titel_text = "\n".join(
        f"{i+1}. {titel}" + (f"\n   Kontext: {beschreibung_liste[i]}" if beschreibung_liste[i] else "")
        for i, titel in enumerate(titel_liste)
    )
    prompt = f"""Du bist ein Nachrichten-Tagger für den Landkreis Fulda (Hessen).
Generiere für jeden Artikel-Titel genau 3-5 kurze deutsche Schlagwörter.
Falls ein Ortsname aus dem Landkreis erkennbar ist, setze diesen als ersten Tag — auch kleinste Dörfer.
Gemeinden: fulda, hünfeld, künzell, petersberg, neuhof, eichenzell, flieden, burghaun, großenlüder, hilders, hofbieber, gersfeld, tann, eiterfeld, rasdorf, dipperz, ebersburg, ehrenberg, hosenfeld, kalbach, nüsttal, poppenhausen.
Ortsteile/Dörfer (Auswahl): rückers, schweben, schmalnau, wehrda, gruben, hünhan, nüst, rothenkirchen, mackenzell, kirchhasel, molzbach, malges, steinbach, pilgerzell, bachrain, horas, johannesberg, maberzell, kämmerzell, bimbach, kleinlüder, uttrichshausen, rommerz, hainzell, blankenau, weyhers, wüstensachsen, sieblos, abtsroda, rodholz, ützhausen, mottgers, großentaft, soisdorf, leibolz, buchenau, arzell, melperts, günthers, lahrbach, neuswarts, dietges, liebhards, simmershausen, löschenrod, kerzell, welkers, haindorf.
Trenne die Tags mit " · ".
Antworte NUR mit den Tags, eine Zeile pro Artikel, keine Nummerierung, keine Erklärungen.

Kategorie-Orientierung – wenn ein Begriff passt, nutze ihn als Tag (hilft bei der automatischen Einordnung):
{_kategorie_hinweis()}

Titel:
{titel_text}"""
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        zeilen = [z.strip() for z in message.content[0].text.strip().split("\n") if z.strip()]
        # Discard lines that look like prose (refusals/explanations) instead of tag lists
        zeilen = [z for z in zeilen if len(z) <= 120 and ('·' in z or len(z.split()) <= 5)]
        zeilen = [z if not _tags_sind_meta(z) else "" for z in zeilen]
        # Return a list aligned by index — avoids key collisions when two articles share a title
        return [zeilen[i] if i < len(zeilen) else "" for i in range(len(titel_liste))]
    except Exception as e:
        print(f"  WARNUNG: Tag-Generierung fehlgeschlagen ({e})")
        return {}

def _html_fallback_verarbeiten(feed, conn):
    """Führt HTML-Fallback aus, falls RSS eines Feeds fehlschlägt oder leer ist."""
    fb = feed["html_fallback"]
    quelle = {**fb, "name": feed["name"], "typ": feed["typ"], "region": feed["region"]}
    return html_quelle_verarbeiten(quelle, conn)


def feed_verarbeiten(feed, conn):
    print(f"\n{'=' * 55}")
    print(f"Abrufen: {feed['name']}")
    try:
        response = requests.get(feed["rss"], headers=HEADERS, timeout=10)
        parsed = feedparser.parse(response.content)
    except Exception as e:
        print(f"  FEHLER: Verbindung fehlgeschlagen ({e})")
        if feed.get("html_fallback"):
            print(f"  → HTML-Fallback wird verwendet...")
            return _html_fallback_verarbeiten(feed, conn)
        return 0, 0

    echte_eintraege = [e for e in parsed.entries if e.get("title", "").strip()]
    if not echte_eintraege and feed.get("html_fallback"):
        print(f"  RSS liefert keine verwertbaren Einträge → HTML-Fallback wird verwendet...")
        return _html_fallback_verarbeiten(feed, conn)

    neu = 0
    duplikate = 0
    neue_artikel = []
    cursor = conn.cursor()

    for entry in echte_eintraege:
        link         = entry.get("link", "")
        titel        = entry.get("title", "").strip()
        datum        = datum_parsen(entry.get("published", ""))
        hash_wert    = artikel_hash(link)
        beschreibung = entry.get("summary", "") or entry.get("description", "") or ""
        beschreibung = auf_zwei_saetze(re.sub(r'<[^>]+>', '', beschreibung).strip())
        if any(dom in link for dom in QUELLEN_META_DESC):
            meta = meta_beschreibung_holen(link)
            if meta:
                beschreibung = meta

        cursor.execute(
            "SELECT id FROM artikel WHERE titel = %s OR hash = %s",
            (titel, hash_wert)
        )
        if cursor.fetchone():
            duplikate += 1
            continue

        try:
            cursor.execute("SAVEPOINT sp1")
            cursor.execute("""
                INSERT INTO artikel
                (hash, titel, link, quelle, typ, region, datum, gespeichert, tags, beschreibung)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                hash_wert, titel, link,
                feed["name"], feed["typ"], feed["region"],
                datum,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                None,
                beschreibung
            ))
            cursor.execute("RELEASE SAVEPOINT sp1")
            neue_artikel.append((hash_wert, titel))
            neu += 1
        except psycopg2.IntegrityError:
            cursor.execute("ROLLBACK TO SAVEPOINT sp1")
            duplikate += 1

    conn.commit()

    if neue_artikel:
        print(f"  Gefunden: {len(parsed.entries)} | Neu: {neu} | Duplikate: {duplikate}")
        print(f"  Generiere Tags für {len(neue_artikel)} Artikel...")
        for i in range(0, len(neue_artikel), 20):
            batch = neue_artikel[i:i + 20]
            batch_hashes = [h for h, _ in batch]
            cursor.execute(
                "SELECT hash, beschreibung FROM artikel WHERE hash = ANY(%s)",
                (batch_hashes,)
            )
            desc_map = {row[0]: row[1] or "" for row in cursor.fetchall()}
            beschreibungen = [desc_map.get(h, "") for h, _ in batch]
            tags_list = tags_generieren([t for _, t in batch], beschreibungen)
            for idx, (hash_wert, titel) in enumerate(batch):
                tags = tags_list[idx] if idx < len(tags_list) else ""
                if tags and not _tags_sind_meta(tags):
                    cursor.execute(
                        "UPDATE artikel SET tags = %s WHERE hash = %s",
                        (tags, hash_wert)
                    )
            conn.commit()
            print(f"  Tags generiert: {min(i + 20, len(neue_artikel))}/{len(neue_artikel)}")
    else:
        print(f"  Gefunden: {len(parsed.entries)} | Neu: 0 | Duplikate: {duplikate}")

    region_aus_tags_verfeinern(neue_artikel, cursor, conn)

    cursor.close()
    return neu, duplikate

def html_artikel_holen(url, base_url):
    """Scrapt eine HTML-Listenseite und gibt (titel, link)-Paare zurück."""
    try:
        session = html_session_erstellen()
        session.headers["Referer"] = base_url + "/"
        r = session.get(url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  FEHLER: HTML-Seite nicht erreichbar ({e})")
        return []

    artikel = []
    gesehen_links = set()

    for match in re.finditer(r'<a\s([^>]*class="[^"]*id-LinkOverlay-link[^"]*"[^>]*)>', r.text):
        attrs = match.group(1)
        href_m = re.search(r'href="([^"]+)"', attrs)
        title_m = re.search(r'title="([^"]+)"', attrs)
        if not (href_m and title_m):
            continue
        link = href_m.group(1)
        if link.startswith('//'):
            link = 'https:' + link
        elif link.startswith('/'):
            link = base_url + link
        if not re.search(r'-\d{5,}\.html$', link):
            continue
        if link in gesehen_links:
            continue
        gesehen_links.add(link)
        titel = html_unescape(title_m.group(1)).strip()
        if titel:
            artikel.append((titel, link, None, ""))

    return artikel


def oz_artikel_holen(url, base_url):
    """Scrapt osthessen-zeitung.de (TYPO3/tx_news) und gibt (titel, link, datum, beschreibung)-Tupel zurück."""
    try:
        session = html_session_erstellen()
        session.headers["Referer"] = base_url + "/"
        r = session.get(url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  FEHLER: HTML-Seite nicht erreichbar ({e})")
        return []

    artikel = []
    gesehen_links = set()

    for teil in r.text.split('class="article articletype-0"')[1:]:
        # Anzeigen überspringen
        cat_m = re.search(r'news-list-category[^>]*>\s*([^<]+)', teil)
        if cat_m and cat_m.group(1).strip().lower() == 'anzeige':
            continue

        titel_m = re.search(r'itemprop="headline"[^>]*>([^<]+)', teil)
        link_m  = re.search(r'href="(einzelansicht/news/[^"]+\.html)"', teil)
        if not (titel_m and link_m):
            continue

        link  = base_url + '/' + link_m.group(1)
        if link in gesehen_links:
            continue
        gesehen_links.add(link)

        titel = html_unescape(titel_m.group(1)).strip()

        date_m = re.search(r'<time datetime="(\d{2}\.\d{2}\.\d{4})"', teil)
        try:
            datum = datetime.strptime(date_m.group(1), '%d.%m.%Y').strftime('%Y-%m-%d %H:%M:%S') if date_m else None
        except ValueError:
            datum = None

        teaser_m = re.search(r'itemprop="description"[^>]*>(.*?)</span>', teil, re.DOTALL)
        beschreibung = auf_zwei_saetze(re.sub(r'<[^>]+>', '', teaser_m.group(1)).strip()) if teaser_m else ""
        beschreibung = html_unescape(beschreibung)

        if titel:
            artikel.append((titel, link, datum, beschreibung))

    return artikel


def _hs_fulda_slug(titel):
    """Baut den TYPO3-URL-Slug aus einem Titel: Kleinschreibung, Umlaute transliterieren, Leerzeichen → Bindestrich."""
    slug = titel.lower().strip()
    # TYPO3 transliteriert deutsche Umlaute
    for src, dst in [('ä','ae'),('ö','oe'),('ü','ue'),('ß','ss')]:
        slug = slug.replace(src, dst)
    slug = re.sub(r'[\s/\\:,;!?\'"()[\]{}]+', '-', slug)
    slug = re.sub(r'[^\w\-]', '', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug


def hs_fulda_artikel_holen(url, base_url):
    """Scrapt Hochschule Fulda Meldungen."""
    try:
        session = html_session_erstellen()
        session.headers["Referer"] = base_url + "/"
        r = session.get(url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  FEHLER: HTML-Seite nicht erreichbar ({e})")
        return []

    artikel = []
    gesehen = set()
    detail_base = "/unsere-hochschule/alle-meldungen/meldungsdetails/detail/"

    # Ansatz 1: Detail-Links direkt im HTML suchen
    for match in re.finditer(
        r'href="(' + re.escape(detail_base) + r'[^"]+)"[^>]*>\s*([^<]{5,150})',
        r.text
    ):
        link  = base_url + match.group(1)
        titel = html_unescape(match.group(2)).strip()
        if link not in gesehen and titel:
            gesehen.add(link)
            nach = r.text[match.end():match.end() + 600]
            teaser_m = re.search(r'<p[^>]*>([^<]+)</p>', nach)
            beschreibung = auf_zwei_saetze(html_unescape(teaser_m.group(1)).strip()) if teaser_m else ""
            artikel.append((titel, link, None, beschreibung))

    # Ansatz 2: Falls keine Links im HTML – Titel aus h3 lesen, Slug generieren
    if not artikel:
        for match in re.finditer(r'<h3[^>]*>(.*?)</h3>', r.text, re.DOTALL):
            titel = html_unescape(re.sub(r'<[^>]+>', ' ', match.group(1)))
            titel = re.sub(r'\s+', ' ', titel).strip()
            if len(titel) < 8:
                continue
            slug = _hs_fulda_slug(titel)
            link = base_url + detail_base + slug
            if link not in gesehen:
                gesehen.add(link)
                nach = r.text[match.end():match.end() + 600]
                teaser_m = re.search(r'<p[^>]*>([^<]+)</p>', nach)
                beschreibung = auf_zwei_saetze(html_unescape(teaser_m.group(1)).strip()) if teaser_m else ""
                artikel.append((titel, link, None, beschreibung))

    return artikel


def wittich_artikel_holen(url, base_url):
    """Scrapt eine Wittich-Gemeindezeitung. url = https://ol.wittich.de/titel/[ID].
    The base URL auto-loads the current issue, so no issue number is needed in config."""
    m_id = re.search(r'/titel/(\d+)', url)
    if not m_id:
        print("  FEHLER: Keine Titel-ID in Wittich-URL gefunden")
        return []
    titel_id = m_id.group(1)

    try:
        session = html_session_erstellen()
        r = session.get(url, timeout=20, allow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        print(f"  FEHLER: Wittich-Seite nicht erreichbar ({e})")
        return []

    # Derive publication date from ISO week embedded in article links
    datum_str = None
    m_ausgabe = re.search(r'/ausgabe/(\d+)/(\d{4})/', r.text)
    if m_ausgabe:
        try:
            ausgabe, jahr = int(m_ausgabe.group(1)), int(m_ausgabe.group(2))
            # Thursday of the ISO week — typical Wittich publication day
            datum_str = datetime.fromisocalendar(jahr, ausgabe, 4).strftime('%Y-%m-%d 08:00:00')
        except (ValueError, AttributeError):
            pass

    artikel = []
    gesehen = set()
    artikel_pattern = re.compile(
        r'<a\s[^>]*href="(/titel/' + re.escape(titel_id) + r'/ausgabe/\d+/\d{4}/artikel/[^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL
    )
    for a_m in artikel_pattern.finditer(r.text):
        link = base_url + a_m.group(1)
        if link in gesehen:
            continue
        gesehen.add(link)

        content = a_m.group(2)
        titel_m = re.search(r'data-role="headline"[^>]*>\s*(.*?)\s*</h\d>', content, re.DOTALL)
        teaser_m = re.search(r'data-role="teaser"[^>]*>(.*?)</div>', content, re.DOTALL)
        if not titel_m:
            continue

        titel = html_unescape(re.sub(r'<[^>]+>', '', titel_m.group(1))).strip()
        beschreibung = auf_zwei_saetze(
            html_unescape(re.sub(r'<[^>]+>', '', teaser_m.group(1))).strip()
        ) if teaser_m else ""

        if not titel or len(titel) < 3:
            continue
        artikel.append((titel, link, datum_str, beschreibung))

    return artikel


def html_quelle_verarbeiten(quelle, conn):
    print(f"\n{'=' * 55}")
    print(f"Abrufen: {quelle['name']} (HTML)")

    parser = quelle.get("parser", "fuldaer_zeitung")
    if parser == "osthessen_zeitung":
        gefundene = oz_artikel_holen(quelle["url"], quelle["base_url"])
    elif parser == "hs_fulda":
        gefundene = hs_fulda_artikel_holen(quelle["url"], quelle["base_url"])
    elif parser == "wittich":
        gefundene = wittich_artikel_holen(quelle["url"], quelle["base_url"])
    else:
        gefundene = html_artikel_holen(quelle["url"], quelle["base_url"])
    if not gefundene:
        print("  Keine Artikel gefunden.")
        return 0, 0

    neu = 0
    duplikate = 0
    neue_artikel = []
    cursor = conn.cursor()
    jetzt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for titel, link, datum, beschreibung in gefundene:
        datum = datum or jetzt
        hash_wert = artikel_hash(link)

        cursor.execute(
            "SELECT id FROM artikel WHERE titel = %s OR hash = %s",
            (titel, hash_wert)
        )
        if cursor.fetchone():
            duplikate += 1
            continue

        try:
            cursor.execute("SAVEPOINT sp1")
            cursor.execute("""
                INSERT INTO artikel
                (hash, titel, link, quelle, typ, region, datum, gespeichert, tags, beschreibung)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                hash_wert, titel, link,
                quelle["name"], quelle["typ"], quelle["region"],
                datum, jetzt,
                None, beschreibung
            ))
            cursor.execute("RELEASE SAVEPOINT sp1")
            neue_artikel.append((hash_wert, titel))
            neu += 1
        except psycopg2.IntegrityError:
            cursor.execute("ROLLBACK TO SAVEPOINT sp1")
            duplikate += 1

    conn.commit()

    if neue_artikel:
        print(f"  Gefunden: {len(gefundene)} | Neu: {neu} | Duplikate: {duplikate}")

        # Fetch meta descriptions for sources that need it (e.g. Fuldaer Zeitung)
        if any(dom in quelle.get("base_url", "") for dom in QUELLEN_META_DESC):
            print(f"  Hole Meta-Beschreibungen für {len(neue_artikel)} Artikel...")
            for hash_wert, _ in neue_artikel:
                cursor.execute(
                    "SELECT link, beschreibung FROM artikel WHERE hash = %s", (hash_wert,)
                )
                row = cursor.fetchone()
                if row and not row[1]:
                    meta = meta_beschreibung_holen(row[0])
                    if meta:
                        cursor.execute(
                            "UPDATE artikel SET beschreibung = %s WHERE hash = %s",
                            (meta, hash_wert)
                        )
            conn.commit()

        print(f"  Generiere Tags für {len(neue_artikel)} Artikel...")
        for i in range(0, len(neue_artikel), 20):
            batch = neue_artikel[i:i + 20]
            batch_hashes = [h for h, _ in batch]
            cursor.execute(
                "SELECT hash, beschreibung FROM artikel WHERE hash = ANY(%s)",
                (batch_hashes,)
            )
            desc_map = {row[0]: row[1] or "" for row in cursor.fetchall()}
            beschreibungen = [desc_map.get(h, "") for h, _ in batch]
            tags_list = tags_generieren([t for _, t in batch], beschreibungen)
            for idx, (hash_wert, titel) in enumerate(batch):
                tags = tags_list[idx] if idx < len(tags_list) else ""
                if tags and not _tags_sind_meta(tags):
                    cursor.execute(
                        "UPDATE artikel SET tags = %s WHERE hash = %s",
                        (tags, hash_wert)
                    )
            conn.commit()
            print(f"  Tags generiert: {min(i + 20, len(neue_artikel))}/{len(neue_artikel)}")
        region_aus_tags_verfeinern(neue_artikel, cursor, conn)
    else:
        print(f"  Gefunden: {len(gefundene)} | Neu: 0 | Duplikate: {duplikate}")

    cursor.close()
    return neu, duplikate


def _tag_anzahl(tags_str):
    return len([t for t in (tags_str or '').split('·') if t.strip()])

def deduplizieren(conn):
    """
    Zwei Pässe:
    1. Exakte Duplikate (gleicher Titel + gleiche Quelle) → behalte den mit mehr Tags.
    2. Ähnliche Titel (≥ 0.85 Ähnlichkeit) gleicher Quelle → behalte den neueren/reicheren
       (fängt Korrekturen wie 'Amokfahrt?' → 'Unfall' oder Tippfehler ab).
    """
    cursor = conn.cursor()
    geloescht_gesamt = 0

    # ── Pass 1: Exakte Duplikate (nur unter den 100 neuesten Artikeln) ─────────
    cursor.execute("""
        SELECT titel, quelle
        FROM (SELECT titel, quelle FROM artikel ORDER BY id DESC LIMIT 100) AS neueste
        GROUP BY titel, quelle
        HAVING COUNT(*) > 1
    """)
    gruppen = cursor.fetchall()

    for titel, quelle in gruppen:
        cursor.execute(
            "SELECT id, tags FROM artikel WHERE titel = %s AND quelle = %s ORDER BY id",
            (titel, quelle)
        )
        eintraege = cursor.fetchall()
        beste_id = max(eintraege, key=lambda e: (_tag_anzahl(e[1]), e[0]))[0]
        for id_, _ in eintraege:
            if id_ != beste_id:
                cursor.execute("DELETE FROM artikel WHERE id = %s", (id_,))
                geloescht_gesamt += 1

    conn.commit()
    if gruppen:
        print(f"  Pass 1 (exakt):  {geloescht_gesamt} Duplikat(e) in {len(gruppen)} Gruppe(n) gelöscht")

    # ── Pass 2: Fuzzy-Duplikate (nur unter den 100 neuesten Artikeln) ──────────
    cursor.execute("""
        SELECT id, titel, tags, gespeichert, quelle
        FROM artikel
        ORDER BY id DESC
        LIMIT 100
    """)
    alle = cursor.fetchall()

    nach_quelle = defaultdict(list)
    for row in alle:
        nach_quelle[row[4]].append(row)   # gruppieren nach quelle

    zum_loeschen = set()
    fuzzy_paare = 0

    for quelle, artikel in nach_quelle.items():
        for i, (id_a, titel_a, tags_a, gesp_a, _) in enumerate(artikel):
            if id_a in zum_loeschen:
                continue
            for id_b, titel_b, tags_b, gesp_b, _ in artikel[i + 1:]:
                if id_b in zum_loeschen:
                    continue
                # Nur prüfen wenn Titel nicht identisch (exakter Pass hat das schon erledigt)
                if titel_a == titel_b:
                    continue
                # Mindestlänge von 12 Zeichen verhindert Fehlalarme bei kurzen Titeln
                if len(titel_a) < 12 or len(titel_b) < 12:
                    continue
                aehnlich = SequenceMatcher(None, titel_a.lower(), titel_b.lower()).ratio()
                if aehnlich >= 0.85:
                    fuzzy_paare += 1
                    # Behalte den mit mehr Tags; bei Gleichstand den neueren (höhere id = später gespeichert)
                    if _tag_anzahl(tags_a) >= _tag_anzahl(tags_b):
                        zum_loeschen.add(id_b)
                        print(f"  Fuzzy-Duplikat [{quelle}]: '{titel_b}' → gelöscht (ähnl. {aehnlich:.0%})")
                    else:
                        zum_loeschen.add(id_a)
                        print(f"  Fuzzy-Duplikat [{quelle}]: '{titel_a}' → gelöscht (ähnl. {aehnlich:.0%})")

    for id_ in zum_loeschen:
        cursor.execute("DELETE FROM artikel WHERE id = %s", (id_,))

    conn.commit()
    cursor.close()

    geloescht_gesamt += len(zum_loeschen)
    if zum_loeschen:
        print(f"  Pass 2 (fuzzy):  {len(zum_loeschen)} Artikel in {fuzzy_paare} Paar(en) gelöscht")
    else:
        print("  Pass 2 (fuzzy):  Keine ähnlichen Duplikate gefunden")

    if geloescht_gesamt == 0:
        print("  Deduplizierung:  Datenbank ist sauber")
    return geloescht_gesamt


def main():
    print("Fulda News Aggregator")
    print(f"Gestartet: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

    conn = db_verbinden()
    datenbank_einrichten(conn)
    _region_retroaktiv_korrigieren(conn)

    gesamt_neu = 0
    gesamt_duplikate = 0

    for feed in FEEDS:
        neu, duplikate = feed_verarbeiten(feed, conn)
        gesamt_neu += neu
        gesamt_duplikate += duplikate

    for quelle in HTML_QUELLEN:
        neu, duplikate = html_quelle_verarbeiten(quelle, conn)
        gesamt_neu += neu
        gesamt_duplikate += duplikate

    print(f"\n{'=' * 55}")
    print("DEDUPLIZIERUNG")
    deduplizieren(conn)

    cursor = conn.cursor()
    print(f"\n{'=' * 55}")
    print("ZUSAMMENFASSUNG")
    print(f"  Neue Artikel gespeichert: {gesamt_neu}")
    print(f"  Duplikate übersprungen:   {gesamt_duplikate}")

    cursor.execute("SELECT COUNT(*) FROM artikel")
    gesamt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM artikel WHERE tags IS NOT NULL AND tags != ''")
    mit_tags = cursor.fetchone()[0]
    print(f"  Artikel gesamt in DB:     {gesamt}")
    print(f"  Davon mit Tags:           {mit_tags}")

    print(f"\n{'=' * 55}")
    print("BEISPIEL-ARTIKEL MIT TAGS:")
    cursor.execute("""
        SELECT titel, tags, quelle, datum
        FROM artikel
        WHERE tags IS NOT NULL AND tags != ''
        ORDER BY datum DESC
        LIMIT 3
    """)
    for titel, tags, quelle, datum in cursor.fetchall():
        print(f"\n  {titel}")
        print(f"  Tags: {tags}")
        print(f"  {quelle} | {datum}")

    cursor.close()

    print(f"\n{'=' * 55}")
    print("PUSH-BENACHRICHTIGUNGEN")
    # 70-minute window: slightly more than the 1-hour cron interval so no articles are missed.
    # Duplicate notifications are prevented at the device level by the push `tag` (= article hash).
    cutoff = (datetime.now() - timedelta(minutes=70)).strftime('%Y-%m-%d %H:%M:%S')
    benachrichtigungen_senden(conn, cutoff)

    print(f"\n{'=' * 55}")
    print("TAG-VALIDIERUNG")
    tags_korrigieren(conn)

    print(f"\n{'=' * 55}")
    print("ARCHIV")
    archiv_generieren(conn)
    sitemap_generieren(conn)
    conn.close()
    print(f"\nFertig!")


REGIONEN_HESSEN = ('hessen', 'osthessen')

BEKANNTE_REGIONEN = (
    # Landkreis (permanent)
    'landkreis-fulda',
    # Gemeinden
    'fulda', 'hünfeld', 'künzell', 'petersberg', 'neuhof', 'eichenzell',
    'flieden', 'burghaun', 'großenlüder', 'hilders', 'hofbieber', 'gersfeld',
    'tann', 'eiterfeld', 'rasdorf', 'dipperz', 'ebersburg', 'ehrenberg',
    'hosenfeld', 'kalbach', 'nüsttal', 'poppenhausen', 'bad salzschlirf',
    # Stadtteile Fulda
    'bernhards', 'besges', 'bronnzell', 'dietershan', 'edelzell', 'frauenberg',
    'fulda-galerie', 'gläserzell', 'haimbach', 'harmerz', 'hochschule fulda', 'horas',
    'innenstadt', 'istergiesel', 'johannesberg', 'kohlhaus', 'kämmerzell', 'lehnerz',
    'lüdermünd', 'maberzell', 'maikes', 'malkes', 'mittelrode', 'neuenberg',
    'niederrode', 'niesig', 'nordend', 'oberrode', 'ostend', 'rodges',
    'sickels', 'südend', 'weimarer tunnel', 'westend', 'zell', 'ziehers',
    'ziehers-nord', 'ziehers-süd', 'zirkenbach',
    # Ortsteile Hünfeld
    'dammersbach', 'großenbach', 'kirchhasel', 'mackenzell', 'malges', 'michelsrombach',
    'molzbach', 'nüst', 'oberfeld', 'oberrombach', 'rossbach', 'rudolphshan',
    'rückers', 'sargenzell',
    # Ortsteile Künzell
    'bachrain', 'dassen', 'dietershausen', 'dirlos', 'engelhelms', 'keulos',
    'pilgerzell', 'wissels',
    # Ortsteile Petersberg
    'almendorf', 'haunedorf', 'marbach', 'margretenhaun', 'steinau', 'steinhaus',
    # Ortsteile Neuhof
    'dorfborn', 'giesel', 'hattenhof', 'hauswurz', 'kauppen', 'motzlar',
    'rommerz', 'schachten', 'tiefengruben',
    # Ortsteile Eichenzell
    'büchenberg', 'döllbach', 'kerzell', 'löschenrod', 'lütter', 'melters',
    'rothemann', 'rönshausen', 'welkers', 'zillbach',
    # Ortsteile Flieden
    'buchenrod', 'döngesmühle', 'höf und haid', 'magdlos', 'rückers', 'schweben',
    'stork', 'struth',
    # Ortsteile Burghaun
    'großenmoor', 'gruben', 'hechelmannskirchen', 'hünhan', 'kleinmoor', 'köhlersmoor',
    'langenschwarz', 'rothenkirchen', 'schlotzau', 'steinbach',
    # Ortsteile Großenlüder
    'bimbach', 'eichenau', 'kleinlüder', 'lütterz', 'müs', 'uffhausen',
    # Ortsteile Hilders
    'batten', 'brand', 'dietges', 'dörmbach', 'eckweisbach', 'liebhards',
    'rupsroth', 'simmershausen', 'unterbernhards', 'wickers',
    # Ortsteile Hofbieber
    'allmus', 'danzwiesen', 'egelmes', 'elters', 'kleinsassen', 'langenberg',
    'langenbieber', 'mahlerts', 'niederbieber', 'obergruben', 'obernüst', 'rödergrund',
    'schackau', 'schwarzbach', 'traisbach', 'wiesen', 'wittges',
    # Ortsteile Gersfeld
    'altenfeld', 'dalherda', 'gichenbach', 'hettenhausen', 'maiersbach', 'mosbach',
    'obernhausen', 'rengersfeld', 'rodenbach', 'rommers', 'sandberg', 'schachen',
    # Ortsteile Tann
    'günthers', 'habel', 'hundsbach', 'lahrbach', 'neuschwammbach', 'neuswarts',
    'schlitzenhausen', 'theobaldshof', 'wendershausen',
    # Ortsteile Eiterfeld
    'arzell', 'betzenrod', 'branders', 'buchenau', 'dittlofrod', 'fürsteneck',
    'giesenhain', 'großentaft', 'körnbach', 'leibolz', 'leimbach', 'mengers',
    'oberweisenborn', 'reckrod', 'soisdorf', 'treischfeld', 'ufhausen', 'unterufhausen',
    'wölf',
    # Ortsteile Rasdorf
    'grüsselbach', 'setzelbach',
    # Ortsteile Dipperz
    'armenhof', 'dörmbach', 'finkenhain', 'friesenhausen', 'kohlgrund', 'wisselsrod',
    'wolferts',
    # Ortsteile Ebersburg
    'ebersberg', 'ried', 'schmalnau', 'thalau', 'weyhers',
    # Ortsteile Ehrenberg
    'melperts', 'reulbach', 'seiferts', 'thaiden', 'wüstensachsen',
    # Ortsteile Hosenfeld
    'blankenau', 'brandlos', 'hainzell', 'jossa', 'pfaffenrod', 'poppenrod',
    'schletzenhausen',
    # Ortsteile Kalbach
    'eichenried', 'heubach', 'mittelkalbach', 'niederkalbach', 'oberkalbach', 'uttrichshausen',
    'veitsteinbach',
    # Ortsteile Nüsttal
    'gotthards', 'haselstein', 'hofaschenbach', 'mittelaschenbach', 'morles', 'oberaschenbach',
    'rimmels', 'silges',
    # Ortsteile Poppenhausen
    'abtsroda', 'gackenhof', 'rodholz', 'steinwand',
)

_BEKANNTE_SET     = set(BEKANNTE_REGIONEN)
_BEKANNTE_SET_SQL = tuple(BEKANNTE_REGIONEN)  # for SQL NOT IN

# Maps every Ortsteil/Stadtteil to its parent Gemeinde key (matching WAPPEN_NAMEN).
# Keep in sync with ORTSTEILE_MAPPING in index.html.
ORTSTEILE_TO_GEMEINDE = {
    # Stadtteile Fulda
    'bernhards': 'fulda', 'besges': 'fulda', 'bronnzell': 'fulda', 'dietershan': 'fulda',
    'edelzell': 'fulda', 'frauenberg': 'fulda', 'fulda-galerie': 'fulda', 'gläserzell': 'fulda',
    'haimbach': 'fulda', 'harmerz': 'fulda', 'hochschule fulda': 'fulda', 'horas': 'fulda',
    'innenstadt': 'fulda', 'istergiesel': 'fulda', 'johannesberg': 'fulda', 'kohlhaus': 'fulda',
    'kämmerzell': 'fulda', 'lehnerz': 'fulda', 'lüdermünd': 'fulda', 'maberzell': 'fulda',
    'maikes': 'fulda', 'malkes': 'fulda', 'mittelrode': 'fulda', 'neuenberg': 'fulda',
    'niederrode': 'fulda', 'niesig': 'fulda', 'nordend': 'fulda', 'oberrode': 'fulda',
    'ostend': 'fulda', 'rodges': 'fulda', 'sickels': 'fulda', 'südend': 'fulda',
    'weimarer tunnel': 'fulda', 'westend': 'fulda', 'zell': 'fulda', 'ziehers': 'fulda',
    'ziehers-nord': 'fulda', 'ziehers-süd': 'fulda', 'zirkenbach': 'fulda',
    # Ortsteile Hünfeld
    'dammersbach': 'hünfeld', 'großenbach': 'hünfeld', 'kirchhasel': 'hünfeld', 'mackenzell': 'hünfeld',
    'malges': 'hünfeld', 'michelsrombach': 'hünfeld', 'molzbach': 'hünfeld', 'nüst': 'hünfeld',
    'oberfeld': 'hünfeld', 'oberrombach': 'hünfeld', 'rossbach': 'hünfeld', 'rudolphshan': 'hünfeld',
    'rückers': 'hünfeld', 'sargenzell': 'hünfeld',
    # Ortsteile Künzell
    'bachrain': 'künzell', 'dassen': 'künzell', 'dietershausen': 'künzell', 'dirlos': 'künzell',
    'engelhelms': 'künzell', 'keulos': 'künzell', 'pilgerzell': 'künzell', 'wissels': 'künzell',
    # Ortsteile Petersberg
    'almendorf': 'petersberg', 'haunedorf': 'petersberg', 'marbach': 'petersberg', 'margretenhaun': 'petersberg',
    'steinau': 'petersberg', 'steinhaus': 'petersberg',
    # Ortsteile Neuhof
    'dorfborn': 'neuhof', 'giesel': 'neuhof', 'hattenhof': 'neuhof', 'hauswurz': 'neuhof',
    'kauppen': 'neuhof', 'motzlar': 'neuhof', 'rommerz': 'neuhof', 'schachten': 'neuhof',
    'tiefengruben': 'neuhof',
    # Ortsteile Eichenzell
    'büchenberg': 'eichenzell', 'döllbach': 'eichenzell', 'kerzell': 'eichenzell', 'löschenrod': 'eichenzell',
    'lütter': 'eichenzell', 'melters': 'eichenzell', 'rothemann': 'eichenzell', 'rönshausen': 'eichenzell',
    'welkers': 'eichenzell', 'zillbach': 'eichenzell',
    # Ortsteile Flieden
    'buchenrod': 'flieden', 'döngesmühle': 'flieden', 'höf und haid': 'flieden', 'magdlos': 'flieden',
    'rückers': 'flieden', 'schweben': 'flieden', 'stork': 'flieden', 'struth': 'flieden',
    # Ortsteile Burghaun
    'großenmoor': 'burghaun', 'gruben': 'burghaun', 'hechelmannskirchen': 'burghaun', 'hünhan': 'burghaun',
    'kleinmoor': 'burghaun', 'köhlersmoor': 'burghaun', 'langenschwarz': 'burghaun', 'rothenkirchen': 'burghaun',
    'schlotzau': 'burghaun', 'steinbach': 'burghaun',
    # Ortsteile Großenlüder
    'bimbach': 'großenlüder', 'eichenau': 'großenlüder', 'kleinlüder': 'großenlüder', 'lütterz': 'großenlüder',
    'müs': 'großenlüder', 'uffhausen': 'großenlüder',
    # Ortsteile Hilders
    'batten': 'hilders', 'brand': 'hilders', 'dietges': 'hilders', 'dörmbach': 'hilders',
    'eckweisbach': 'hilders', 'liebhards': 'hilders', 'rupsroth': 'hilders', 'simmershausen': 'hilders',
    'unterbernhards': 'hilders', 'wickers': 'hilders',
    # Ortsteile Hofbieber
    'allmus': 'hofbieber', 'danzwiesen': 'hofbieber', 'egelmes': 'hofbieber', 'elters': 'hofbieber',
    'kleinsassen': 'hofbieber', 'langenberg': 'hofbieber', 'langenbieber': 'hofbieber', 'mahlerts': 'hofbieber',
    'niederbieber': 'hofbieber', 'obergruben': 'hofbieber', 'obernüst': 'hofbieber', 'rödergrund': 'hofbieber',
    'schackau': 'hofbieber', 'schwarzbach': 'hofbieber', 'traisbach': 'hofbieber', 'wiesen': 'hofbieber',
    'wittges': 'hofbieber',
    # Ortsteile Gersfeld
    'altenfeld': 'gersfeld', 'dalherda': 'gersfeld', 'gichenbach': 'gersfeld', 'hettenhausen': 'gersfeld',
    'maiersbach': 'gersfeld', 'mosbach': 'gersfeld', 'obernhausen': 'gersfeld', 'rengersfeld': 'gersfeld',
    'rodenbach': 'gersfeld', 'rommers': 'gersfeld', 'sandberg': 'gersfeld', 'schachen': 'gersfeld',
    # Ortsteile Tann
    'günthers': 'tann', 'habel': 'tann', 'hundsbach': 'tann', 'lahrbach': 'tann',
    'neuschwammbach': 'tann', 'neuswarts': 'tann', 'schlitzenhausen': 'tann', 'theobaldshof': 'tann',
    'wendershausen': 'tann',
    # Ortsteile Eiterfeld
    'arzell': 'eiterfeld', 'betzenrod': 'eiterfeld', 'branders': 'eiterfeld', 'buchenau': 'eiterfeld',
    'dittlofrod': 'eiterfeld', 'fürsteneck': 'eiterfeld', 'giesenhain': 'eiterfeld', 'großentaft': 'eiterfeld',
    'körnbach': 'eiterfeld', 'leibolz': 'eiterfeld', 'leimbach': 'eiterfeld', 'mengers': 'eiterfeld',
    'oberweisenborn': 'eiterfeld', 'reckrod': 'eiterfeld', 'soisdorf': 'eiterfeld', 'treischfeld': 'eiterfeld',
    'ufhausen': 'eiterfeld', 'unterufhausen': 'eiterfeld', 'wölf': 'eiterfeld',
    # Ortsteile Rasdorf
    'grüsselbach': 'rasdorf', 'setzelbach': 'rasdorf',
    # Ortsteile Dipperz
    'armenhof': 'dipperz', 'dörmbach': 'dipperz', 'finkenhain': 'dipperz', 'friesenhausen': 'dipperz',
    'kohlgrund': 'dipperz', 'wisselsrod': 'dipperz', 'wolferts': 'dipperz',
    # Ortsteile Ebersburg
    'ebersberg': 'ebersburg', 'ried': 'ebersburg', 'schmalnau': 'ebersburg', 'thalau': 'ebersburg',
    'weyhers': 'ebersburg',
    # Ortsteile Ehrenberg
    'melperts': 'ehrenberg', 'reulbach': 'ehrenberg', 'seiferts': 'ehrenberg', 'thaiden': 'ehrenberg',
    'wüstensachsen': 'ehrenberg',
    # Ortsteile Hosenfeld
    'blankenau': 'hosenfeld', 'brandlos': 'hosenfeld', 'hainzell': 'hosenfeld', 'jossa': 'hosenfeld',
    'pfaffenrod': 'hosenfeld', 'poppenrod': 'hosenfeld', 'schletzenhausen': 'hosenfeld',
    # Ortsteile Kalbach
    'eichenried': 'kalbach', 'heubach': 'kalbach', 'mittelkalbach': 'kalbach', 'niederkalbach': 'kalbach',
    'oberkalbach': 'kalbach', 'uttrichshausen': 'kalbach', 'veitsteinbach': 'kalbach',
    # Ortsteile Nüsttal
    'gotthards': 'nüsttal', 'haselstein': 'nüsttal', 'hofaschenbach': 'nüsttal', 'mittelaschenbach': 'nüsttal',
    'morles': 'nüsttal', 'oberaschenbach': 'nüsttal', 'rimmels': 'nüsttal', 'silges': 'nüsttal',
    # Ortsteile Poppenhausen
    'abtsroda': 'poppenhausen', 'gackenhof': 'poppenhausen', 'rodholz': 'poppenhausen', 'steinwand': 'poppenhausen',

}


def _region_aus_tag_bestimmen(tag_norm):
    """Resolve a normalised tag to a Gemeinde key, or None if not a known place.
    Checks Gemeinden first, then resolves Ortsteile to their parent Gemeinde."""
    if tag_norm in WAPPEN_NAMEN:
        return tag_norm
    return ORTSTEILE_TO_GEMEINDE.get(tag_norm)


def _region_retroaktiv_korrigieren(conn):
    """Fix existing articles whose tags contain a known Gemeinde/Ortsteil
    but whose region is still set to a broad value (hessen, osthessen, landkreis-fulda, etc.).
    Safe to run on every aggregator start — only updates rows that need it."""
    cursor = conn.cursor()

    # Reset any Ortsteil-level regions (e.g. 'rückers') back to 'landkreis-fulda'
    # so the loop below can re-promote them correctly to the parent Gemeinde.
    GEMEINDEN = tuple(WAPPEN_NAMEN.keys()) + ('landkreis-fulda', 'hessen', 'osthessen')
    cursor.execute(
        "UPDATE artikel SET region = 'landkreis-fulda'"
        " WHERE region NOT IN %s AND region IS NOT NULL AND region != ''",
        (GEMEINDEN,)
    )
    if cursor.rowcount:
        print(f"  Ortsteil-Regionen zurückgesetzt: {cursor.rowcount} Artikel")

    cursor.execute(
        "SELECT hash, tags FROM artikel WHERE tags IS NOT NULL AND tags != ''"
        " AND (region IS NULL OR region NOT IN %s)",
        (_BEKANNTE_SET_SQL,)
    )
    rows = cursor.fetchall()
    updated = 0
    for hash_wert, tags_str in rows:
        for tag in tags_str.split('·'):
            ziel = _region_aus_tag_bestimmen(tag.strip().lower())
            if ziel:
                cursor.execute(
                    "UPDATE artikel SET region = %s WHERE hash = %s",
                    (ziel, hash_wert)
                )
                updated += 1
                break
    conn.commit()
    cursor.close()
    if updated:
        print(f"  Regionen korrigiert (retroaktiv): {updated} Artikel")


def region_aus_tags_verfeinern(neue_artikel, cursor, conn):
    """Upgrades an article's region to a specific Gemeinde when the AI-assigned
    tags contain a matching place name (Gemeinde or Ortsteil → parent Gemeinde).
    This prevents Hessen/Osthessen articles tagged with a local place from being
    archived after 14 days."""
    if not neue_artikel:
        return
    BROAD = {'hessen', 'osthessen', 'landkreis-fulda', None}
    hashes = [h for h, _ in neue_artikel]
    cursor.execute(
        "SELECT hash, tags, region FROM artikel WHERE hash = ANY(%s)",
        (hashes,)
    )
    rows = cursor.fetchall()
    updates = []
    for hash_wert, tags_roh, region in rows:
        if region not in BROAD or not tags_roh:
            continue
        for tag in tags_roh.split('·'):
            ziel = _region_aus_tag_bestimmen(tag.strip().lower())
            if ziel:
                updates.append((ziel, hash_wert))
                break
    for ziel, hash_wert in updates:
        cursor.execute("UPDATE artikel SET region = %s WHERE hash = %s", (ziel, hash_wert))
    conn.commit()
    if updates:
        print(f"  Regionen verfeinert: {len(updates)} Artikel auf Gemeinde-Ebene angehoben")


_TAGS_META_MUSTER = [
    'keine tags', 'kein ortstag', 'kein orts', 'nicht im landkreis',
    'deshalb kein', 'außerhalb', 'nicht erkennbar', 'nicht möglich',
    'kein ort', 'keine ortschaft', 'leider', 'entschuldigung',
    'tut mir leid', 'ist nicht', 'keine angabe', 'nicht zuordenbar',
]

def _tags_sind_meta(tags_str):
    """True if the string looks like an AI refusal/explanation rather than actual tags."""
    t = (tags_str or '').lower()
    return any(m in t for m in _TAGS_META_MUSTER)


def _tags_plausibel(tags_str, titel, beschreibung):
    """True if at least one tag (or a 5+-char word from a tag) appears in title+description.
    A complete mismatch — zero overlap — is the signature of a tag-swap bug."""
    combined = (titel + " " + beschreibung).lower()
    for tag in tags_str.split('·'):
        tag_lower = tag.strip().lower()
        if not tag_lower:
            continue
        if tag_lower in combined:
            return True
        for word in tag_lower.split():
            if len(word) >= 5 and word in combined:
                return True
    return False


def tags_korrigieren(conn):
    """Detects articles whose tags have zero overlap with their own title+description
    (= likely a tag-swap from the batch write) and re-generates them."""
    cursor = conn.cursor()

    # ── Schritt 1: Meta-Antworten der KI aus der DB entfernen ──
    cursor.execute("SELECT hash, tags FROM artikel WHERE tags IS NOT NULL AND tags != ''")
    meta_hashes = [h for h, t in cursor.fetchall() if _tags_sind_meta(t)]
    if meta_hashes:
        cursor.executemany("UPDATE artikel SET tags = '' WHERE hash = %s", [(h,) for h in meta_hashes])
        conn.commit()
        print(f"  Tags-Bereinigung: {len(meta_hashes)} Meta-Antworten gelöscht")

    cursor.execute("""
        SELECT hash, titel, beschreibung, tags FROM artikel
        WHERE tags IS NOT NULL AND tags != ''
          AND beschreibung IS NOT NULL AND beschreibung != ''
          AND gespeichert > TO_CHAR(NOW() - INTERVAL '30 days', 'YYYY-MM-DD HH24:MI:SS')
    """)
    rows = cursor.fetchall()

    zu_korrigieren = [
        (hash_wert, titel, beschreibung)
        for hash_wert, titel, beschreibung, tags in rows
        if not _tags_plausibel(tags, titel, beschreibung)
    ][:50]  # cap per run to control API cost

    if not zu_korrigieren:
        cursor.close()
        return

    print(f"  Tags-Korrektur: {len(zu_korrigieren)} Artikel mit falsch zugeordneten Tags")
    korrigiert = 0
    for i in range(0, len(zu_korrigieren), 20):
        batch = zu_korrigieren[i:i + 20]
        tags_list = tags_generieren([t for _, t, _ in batch], [d for _, _, d in batch])
        for idx, (hash_wert, _, _) in enumerate(batch):
            tags = tags_list[idx] if idx < len(tags_list) else ""
            if tags:
                cursor.execute("UPDATE artikel SET tags = %s WHERE hash = %s", (tags, hash_wert))
                korrigiert += 1
        conn.commit()

    cursor.close()
    print(f"  Tags-Korrektur: {korrigiert} Artikel neu getaggt")


def archiv_generieren(conn):
    """Generates static archiv/seite-N.html pages for:
    - Unknown-region articles older than 7 days
    - Hessen/Osthessen articles older than 14 days
    """
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    alle_bekannten = BEKANNTE_REGIONEN + REGIONEN_HESSEN

    cursor.execute("""
        SELECT COUNT(*) FROM artikel
        WHERE (
            (region IS NULL OR region NOT IN %s)
            AND datum < TO_CHAR(NOW() - INTERVAL '7 days', 'YYYY-MM-DD HH24:MI:SS')
        ) OR (
            region = ANY(%s)
            AND datum < TO_CHAR(NOW() - INTERVAL '14 days', 'YYYY-MM-DD HH24:MI:SS')
        )
    """, (alle_bekannten, list(REGIONEN_HESSEN)))
    gesamt = cursor.fetchone()["count"]

    LIMIT = 50
    seiten_gesamt = max(1, (gesamt + LIMIT - 1) // LIMIT)

    archiv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archiv")
    os.makedirs(archiv_dir, exist_ok=True)

    for seite in range(1, seiten_gesamt + 1):
        offset = (seite - 1) * LIMIT
        cursor.execute("""
            SELECT titel, link, quelle, region, datum, beschreibung, tags
            FROM artikel
            WHERE (
                (region IS NULL OR region NOT IN %s)
                AND datum < TO_CHAR(NOW() - INTERVAL '7 days', 'YYYY-MM-DD HH24:MI:SS')
            ) OR (
                region = ANY(%s)
                AND datum < TO_CHAR(NOW() - INTERVAL '14 days', 'YYYY-MM-DD HH24:MI:SS')
            )
            ORDER BY datum DESC
            LIMIT %s OFFSET %s
        """, (alle_bekannten, list(REGIONEN_HESSEN), LIMIT, offset))
        artikel = cursor.fetchall()
        html = _archiv_seite_html(artikel, seite, seiten_gesamt, gesamt)
        pfad = os.path.join(archiv_dir, f"seite-{seite}.html")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(html)

    cursor.close()
    print(f"  Archiv generiert: {seiten_gesamt} Seite(n), {gesamt} Artikel → archiv/")
    return seiten_gesamt


_KAT_REGELN = [
    ("Vorfälle",              "#c53030", ["unfall","brand","polizei","einbruch","gewalt","verletzt","blaulicht","einsatz","mord","diebstahl","täter","festnahme","vermisst","notfall","crash"]),
    ("Politik & Verwaltung",  "#1e429f", ["politik","verwaltung","bürgermeister","gemeinderat","kreistag","partei","minister","wahl","sitzung","haushalt","beschluss"]),
    ("Wirtschaft & Arbeit",   "#065f46", ["wirtschaft","unternehmen","jobs","arbeit","betrieb","firma","insolvenz","investition","gewerbe","handel"]),
    ("Sport",                 "#7e3af2", ["sport","fußball","turnier","meisterschaft","liga","trainer","spieler","sieg","niederlage","handball","leichtathletik"]),
    ("Kultur & Freizeit",     "#d97706", ["kultur","veranstaltung","festival","ausstellung","konzert","theater","museum","kunst","freizeit","messe"]),
    ("Bildung & Familie",     "#0284c7", ["schule","bildung","kita","kindergarten","studium","familie","jugend","ausbildung","lehrer","universität"]),
    ("Natur & Umwelt",        "#15803d", ["natur","umwelt","klima","wald","tier","wetter","hochwasser","nachhaltigkeit","energie","solaranlage"]),
    ("Verkehr & Bau",         "#92400e", ["verkehr","straße","bau","baustelle","brücke","autobahn","zug","bus","radweg","parkplatz"]),
    ("Gesundheit",            "#be185d", ["gesundheit","krankenhaus","arzt","medizin","impfung","pflege","klinik","therapie","apotheke"]),
]

def _kategorie_bestimmen(titel, tags):
    text = ((titel or "") + " " + (tags or "")).lower()
    bestes = ("Sonstiges", "#6b7280")
    bester_score = 0
    for name, farbe, keys in _KAT_REGELN:
        score = sum(3 if k in ["unfall","brand","polizei","mord","blaulicht"] and k in text else
                    (1 if k in text else 0) for k in keys)
        if score > bester_score:
            bester_score, bestes = score, (name, farbe)
    return bestes


def _archiv_seite_html(artikel, seite, seiten_gesamt, gesamt):
    from html import escape

    def fmt_datum(d):
        try:
            return datetime.fromisoformat(d.replace(" ", "T")).strftime("%d.%m.%Y")
        except Exception:
            return d or ""

    def fmt_zeit(d):
        try:
            dt = datetime.fromisoformat(d.replace(" ", "T"))
            delta = datetime.now() - dt
            if delta.days == 0:
                h = delta.seconds // 3600
                return f"vor {h} Std." if h else "vor kurzem"
            if delta.days == 1:
                return "gestern"
            if delta.days < 7:
                return f"vor {delta.days} Tagen"
            return fmt_datum(d)
        except Exception:
            return fmt_datum(d)

    canon = f"https://www.rnfulda.de/archiv/seite-{seite}.html"

    karten_html = ""
    for a in artikel:
        titel  = escape(a["titel"] or "")
        quelle = escape(a["quelle"] or "")
        link   = a["link"] or "#"
        datum_iso = (a["datum"] or "")[:10]
        zeit   = escape(fmt_zeit(a["datum"] or ""))
        kat_name, kat_farbe = _kategorie_bestimmen(a["titel"], a["tags"])

        tags_html = ""
        if a["tags"]:
            pills = [escape(t.strip()) for t in a["tags"].split("·") if t.strip()][:5]
            tags_html = '<div class="karte-tags">' + "".join(f'<span class="tag-pill">{p}</span>' for p in pills) + "</div>"

        karten_html += f"""<div class="karte">
  <a href="{link}" target="_blank" rel="noopener" class="karte-bild-link">
    <div class="karte-bild" style="background:{kat_farbe}18">
      <span class="badge" style="background:{kat_farbe}">↗ {escape(kat_name)}</span>
    </div>
  </a>
  <div class="karte-inhalt">
    <a href="{link}" target="_blank" rel="noopener" class="karte-titel-link">
      <div class="karte-titel">{titel}</div>
    </a>
    {tags_html}
    <div class="karte-meta">
      <svg viewBox="0 0 24 24" stroke-width="2" style="width:12px;height:12px;stroke:#666;fill:none;flex-shrink:0"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg>
      <time datetime="{datum_iso}">{zeit}</time>
      <span class="meta-trenner">·</span>
      <span>{quelle}</span>
    </div>
  </div>
  <div class="karte-footer">
    <a href="{link}" target="_blank" rel="noopener" class="lese-link">Ganzen Artikel lesen <svg viewBox="0 0 24 24" stroke-width="2" style="width:13px;height:13px;stroke:currentColor;fill:none"><path d="M5 12h14M12 5l7 7-7 7"/></svg></a>
  </div>
</div>"""

    prev_link = f'<a href="seite-{seite-1}.html" rel="prev">← Neuere</a>' if seite > 1 else ""
    next_link = f'<a href="seite-{seite+1}.html" rel="next">Ältere →</a>' if seite < seiten_gesamt else ""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nachrichtenarchiv Seite {seite} – RegioNachrichten Fulda</title>
<meta name="description" content="Ältere Nachrichten aus dem Landkreis Fulda und Osthessen – Archiv Seite {seite} von {seiten_gesamt} ({gesamt} Artikel gesamt).">
<link rel="canonical" href="{canon}">
{f'<link rel="prev" href="seite-{seite-1}.html">' if seite > 1 else ''}
{f'<link rel="next" href="seite-{seite+1}.html">' if seite < seiten_gesamt else ''}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Source+Sans+3:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{--rot:#c0152a;--border:#e0e0e0;--weiss:#fff;--schwarz:#111;--grau-dunkel:#333;--grau-mittel:#666;--grau-hell:#f4f4f4;--font-display:'Playfair Display',Georgia,serif;--font-body:'Source Sans 3',sans-serif}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:var(--font-body);background:var(--grau-hell);color:var(--schwarz);min-height:100vh}}
header{{background:var(--weiss);border-bottom:1px solid var(--border);padding:0 1.5rem;height:60px;display:flex;align-items:center;gap:10px}}
.logo-icon{{width:36px;height:36px;background:var(--rot);border-radius:8px;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.logo-icon svg{{width:20px;height:20px;fill:#fff}}
.logo-text{{font-family:var(--font-display);font-size:1.1rem;line-height:1.1}}
.logo-text span:first-child{{color:var(--rot)}}
.logo-ort{{font-size:.75rem;color:var(--grau-mittel);font-family:var(--font-body);font-weight:500}}
.back-btn{{margin-left:auto;display:flex;align-items:center;gap:6px;padding:7px 14px;border-radius:7px;border:1px solid var(--border);background:none;font-family:var(--font-body);font-size:.85rem;font-weight:600;color:var(--grau-dunkel);cursor:pointer;text-decoration:none;transition:border-color .15s,color .15s}}
.back-btn:hover{{border-color:var(--rot);color:var(--rot)}}
main{{max-width:1200px;margin:0 auto;padding:1.5rem 1.5rem 4rem}}
h1{{font-family:var(--font-display);font-size:1.5rem;margin-bottom:.2rem}}
.sub{{color:var(--grau-mittel);font-size:.875rem;margin-bottom:1.5rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1.25rem;margin-bottom:2rem}}
.karte{{border:1px solid var(--border);border-radius:12px;overflow:hidden;background:var(--weiss);display:flex;flex-direction:column;transition:box-shadow .2s,transform .2s}}
.karte:hover{{box-shadow:0 8px 24px rgba(0,0,0,.1);transform:translateY(-2px)}}
.karte-bild-link{{display:block;text-decoration:none}}
.karte-bild{{height:80px;display:flex;align-items:flex-end;padding:.6rem;position:relative}}
.badge{{font-size:.62rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;padding:3px 9px;border-radius:4px;color:#fff}}
.karte-inhalt{{padding:.9rem 1rem;flex:1;display:flex;flex-direction:column;gap:.5rem}}
.karte-titel-link{{text-decoration:none;color:inherit}}
.karte-titel{{font-family:var(--font-display);font-size:.95rem;font-weight:700;line-height:1.35;color:var(--schwarz);display:-webkit-box;-webkit-line-clamp:3;line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}
.karte-titel-link:hover .karte-titel{{color:var(--rot)}}
.karte-tags{{display:flex;flex-wrap:wrap;gap:4px;margin-top:2px}}
.tag-pill{{font-size:.65rem;background:#f0f0f0;color:var(--grau-dunkel);padding:2px 7px;border-radius:10px;border:1px solid var(--border)}}
.karte-meta{{display:flex;flex-wrap:wrap;gap:.3rem;font-size:.72rem;color:var(--grau-mittel);align-items:center;padding-top:.4rem;border-top:1px solid var(--border);margin-top:auto}}
.meta-trenner{{opacity:.4}}
.karte-footer{{padding:.7rem 1rem;border-top:1px solid var(--border)}}
.lese-link{{display:flex;align-items:center;gap:.35rem;font-size:.8rem;font-weight:600;color:var(--rot);text-decoration:none}}
.lese-link:hover{{text-decoration:underline}}
nav.pagination{{display:flex;justify-content:space-between;align-items:center;margin:1.5rem 0;font-size:.875rem}}
nav.pagination a{{color:var(--rot);text-decoration:none;font-weight:600}}
nav.pagination a:hover{{text-decoration:underline}}
footer{{border-top:1px solid var(--border);background:var(--weiss);padding:1.5rem;text-align:center;font-size:.8rem;color:var(--grau-mittel)}}
footer a{{color:var(--rot);text-decoration:none}}
@media(max-width:600px){{main{{padding:1rem 1rem 3rem}}.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<header>
  <div class="logo-icon"><svg viewBox="0 0 24 24"><path d="M4 4h16v3H4zm0 5h10v2H4zm0 4h16v2H4zm0 4h10v2H4z"/></svg></div>
  <div class="logo-text">Regio<span>Nachrichten</span><span class="logo-ort">Fulda</span></div>
  <a href="../index.html" class="back-btn"><svg viewBox="0 0 24 24" style="width:13px;height:13px;stroke:currentColor;fill:none;stroke-width:2"><polyline points="15 18 9 12 15 6"/></svg> Startseite</a>
</header>
<main>
  <h1>Nachrichtenarchiv</h1>
  <p class="sub">Seite {seite} von {seiten_gesamt} · {gesamt:,} archivierte Artikel · <a href="../archiv.html" style="color:var(--rot)">Archiv-Übersicht</a></p>
  <div class="grid">
{karten_html}
  </div>
  <nav class="pagination">
    <span>{prev_link}</span>
    <span style="color:var(--grau-mittel)">Seite {seite} / {seiten_gesamt}</span>
    <span>{next_link}</span>
  </nav>
</main>
<footer>RegioNachrichten Fulda · <a href="../archiv.html">Archiv</a> · <a href="../seiten/impressum.html">Impressum</a> · <a href="../seiten/datenschutz.html">Datenschutz</a></footer>
</body>
</html>"""


def sitemap_generieren(conn):
    """Regeneriert sitemap.xml mit allen statischen und Ort/Kategorie-Filterseiten."""

    STATIC_URLS = [
        ("https://www.rnfulda.de",                                  "hourly", "1.0"),
        ("https://www.rnfulda.de/seiten/impressum.html",             "yearly", "0.3"),
        ("https://www.rnfulda.de/seiten/datenschutz.html",          "yearly", "0.3"),
        ("https://www.rnfulda.de/archiv.html",                      "weekly", "0.6"),
        # ?ort=landkreis-fulda weggelassen — Homepage ist bereits die Landkreis-Ansicht
        ("https://www.rnfulda.de/?ort=fulda",                       "hourly", "0.9"),
        ("https://www.rnfulda.de/?ort=h%C3%BCnfeld",                "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=k%C3%BCnzell",                "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=petersberg",                  "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=neuhof",                      "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=eichenzell",                  "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=flieden",                     "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=burghaun",                    "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=gro%C3%9Fenl%C3%BCder",       "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=hilders",                     "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=hofbieber",                   "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=gersfeld",                    "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=tann",                        "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=eiterfeld",                   "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=rasdorf",                     "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=dipperz",                     "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=ebersburg",                   "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=ehrenberg",                   "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=hosenfeld",                   "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=kalbach",                     "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=n%C3%BCsttal",                "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=poppenhausen",                "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=bad%20salzschlirf",           "daily",  "0.7"),
        ("https://www.rnfulda.de/?ort=hessen",                      "hourly", "0.6"),
        ("https://www.rnfulda.de/?kategorie=Vorf%C3%A4lle","hourly", "0.8"),
        ("https://www.rnfulda.de/?kategorie=Politik%20%26%20Verwaltung", "daily", "0.7"),
        ("https://www.rnfulda.de/?kategorie=Wirtschaft%20%26%20Arbeit",  "daily", "0.7"),
        ("https://www.rnfulda.de/?kategorie=Sport",                 "daily",  "0.7"),
        ("https://www.rnfulda.de/?kategorie=Kultur%20%26%20Freizeit",    "daily", "0.7"),
        ("https://www.rnfulda.de/?kategorie=Bildung%20%26%20Familie",    "daily", "0.7"),
        ("https://www.rnfulda.de/?kategorie=Natur%20%26%20Umwelt",       "daily", "0.7"),
        ("https://www.rnfulda.de/?kategorie=Verkehr%20%26%20Bau",        "daily", "0.7"),
        ("https://www.rnfulda.de/?kategorie=Gesundheit",            "daily",  "0.7"),
    ]

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
             '',
             '  <!-- Statische Seiten & Filter -->']
    for loc, freq, prio in STATIC_URLS:
        lines += [f'  <url>', f'    <loc>{loc}</loc>',
                  f'    <changefreq>{freq}</changefreq>',
                  f'    <priority>{prio}</priority>', f'  </url>']

    # Archive pages — enumerate generated files
    archiv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archiv")
    archiv_seiten = []
    if os.path.isdir(archiv_dir):
        import glob as _glob
        archiv_seiten = sorted(_glob.glob(os.path.join(archiv_dir, "seite-*.html")))

    if archiv_seiten:
        lines += ['', f'  <!-- Archiv-Seiten ({len(archiv_seiten)} Seiten) -->']
        for pfad in archiv_seiten:
            dateiname = os.path.basename(pfad)
            lines += [f'  <url>',
                      f'    <loc>https://www.rnfulda.de/archiv/{dateiname}</loc>',
                      f'    <changefreq>weekly</changefreq>',
                      f'    <priority>0.4</priority>',
                      f'  </url>']

    lines += ['', '</urlset>', '']

    sitemap_pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sitemap.xml')
    with open(sitemap_pfad, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"  Sitemap aktualisiert: {len(STATIC_URLS)} statische URLs + Archiv-Seiten → sitemap.xml")

if __name__ == "__main__":
    main()