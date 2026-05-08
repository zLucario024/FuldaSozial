"""
Fulda News API
==============
Stellt die gespeicherten Artikel aus der Datenbank als API bereit.

Starten:
    uvicorn api:app --reload
"""

import os
import json
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, Query, BackgroundTasks, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

# Hessen/Osthessen articles stay on the main page for 14 days, then go to archive.
REGIONEN_HESSEN = ('hessen', 'osthessen')

# Regions shown on the main page permanently (Gemeinden, Landkreis, Stadtteile, Dörfer).
# Articles whose region is not in this set AND not in REGIONEN_HESSEN are
# considered "Alle"-only and archived after 7 days.
BEKANNTE_REGIONEN = (
    # Landkreis (permanent)
    'landkreis-fulda',
    # Gemeinden
    'fulda', 'hünfeld', 'künzell', 'petersberg', 'neuhof', 'eichenzell',
    'flieden', 'burghaun', 'großenlüder', 'hilders', 'hofbieber', 'gersfeld',
    'tann', 'eiterfeld', 'rasdorf', 'dipperz', 'ebersburg', 'ehrenberg',
    'hosenfeld', 'kalbach', 'nüsttal', 'poppenhausen', 'bad salzschlirf',
    # Stadtteile Fulda
    'aschenberg', 'bernhards', 'besges', 'bronnzell', 'dietershan', 'döllbach',
    'edelzell', 'frauenberg', 'fulda-galerie', 'gläserzell', 'haimbach', 'harmerz',
    'hochschule fulda', 'horas', 'innenstadt', 'istergiesel', 'johannesberg', 'kohlhaus',
    'kämmerzell', 'lehnerz', 'lüdermünd', 'maberzell', 'maikes', 'malkes',
    'mittelrode', 'neuenberg', 'niederrode', 'niesig', 'nordend', 'oberrode',
    'ostend', 'rodges', 'roßberg', 'sickels', 'südend', 'süßenbach',
    'uffhausen', 'weimarer tunnel', 'westend', 'ziehers', 'ziehers-nord', 'ziehers-süd',
    # Ortsteile Hünfeld
    'großenbach', 'kirchhasel', 'mackenzell', 'malges', 'molzbach', 'steinbach',
    # Ortsteile Künzell
    'bachrain', 'dassen', 'dietershausen', 'dirlos', 'engelhelms', 'haunes',
    'keulos', 'pilgerzell',
    # Ortsteile Petersberg
    'almendorf', 'böckels', 'dalherda', 'großsassen', 'habelsbach', 'haunedorf',
    'kesselbach', 'kleinsassen', 'marbach', 'margretenhaun', 'melzdorf', 'orferode',
    'rex', 'roßbach', 'steinau', 'steinhaus', 'stöckels', 'untergötzenhof',
    # Ortsteile Neuhof
    'dorfborn', 'giesel', 'hattenhof', 'hauswurz', 'kauppen', 'motzlar',
    'rommerz', 'schachten', 'tiefengruben',
    # Ortsteile Eichenzell
    'kerzell', 'löschenrod', 'lütter', 'rothemann', 'rönshausen', 'welkers',
    'wissels', 'zirkenbach',
    # Ortsteile Flieden
    'buchenrod', 'döngesmühle', 'haindorf', 'höf und haid', 'kohlgrund', 'magdlos',
    'rückers', 'schweben', 'stork', 'struth',
    # Ortsteile Burghaun
    'gruben', 'hettenhausen', 'hünhan', 'nüst', 'rothenkirchen', 'schmalnau',
    'steens', 'thälau', 'wehrda',
    # Ortsteile Großenlüder
    'bimbach', 'kleinlüder', 'müs', 'uttrichshausen',
    # Ortsteile Hilders
    'dietges', 'gehilf', 'liebhards', 'simmershausen', 'unterweid', 'wickers',
    # Ortsteile Hofbieber
    'langenbieber', 'mittelbieber', 'niederbieber', 'schwarzbach', 'traisbach',
    # Ortsteile Gersfeld
    'findlos', 'habelsdorf', 'melperts', 'obernhausen', 'schachen', 'seifertshausen',
    # Ortsteile Tann
    'dippach', 'günthers', 'lahrbach', 'neuswarts',
    # Ortsteile Eiterfeld
    'arzell', 'buchenau', 'großentaft', 'leibolz', 'soisdorf',
    # Ortsteile Rasdorf
    'habel', 'setzelbach',
    # Ortsteile Dipperz
    'dörnhagen',
    # Ortsteile Ebersburg
    'euters', 'götzenhof', 'thalau', 'weyhers',
    # Ortsteile Ehrenberg
    'reulbach', 'seiferts', 'wüstensachsen',
    # Ortsteile Hosenfeld
    'altenhof', 'blankenau', 'brandlos', 'büchenberg', 'eichenberg', 'hainzell',
    'jossa', 'mittelhaun', 'pfaffenrod', 'poppenrod', 'schletzenhausen',
    # Ortsteile Kalbach
    'eichenried', 'heubach', 'mittelkalbach', 'niederkalbach', 'oberkalbach', 'uttrichshausen',
    'veitsteinbach',
    # Ortsteile Nüsttal
    'hofaschenbach', 'morles', 'mottgers', 'ützhausen',
    # Ortsteile Poppenhausen
    'abtsroda', 'rodholz', 'sieblos',
)
_REGIONEN_SQL = tuple(BEKANNTE_REGIONEN)
_ALLE_BEKANNTEN_SQL = _REGIONEN_SQL + REGIONEN_HESSEN


def db_verbinden():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    return conn


app = FastAPI(
    title="Fulda News API",
    description="Regionale Nachrichten aus dem Landkreis Fulda",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PushAbo(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    heimat: str

class PushHeimat(BaseModel):
    endpoint: str
    heimat: str

class FcmAbo(BaseModel):
    fcm_token: str
    heimat: str


@app.get("/")
def startseite():
    return {
        "status": "aktiv",
        "name": "Fulda News API",
        "endpunkte": ["/artikel", "/quellen", "/statistik", "/docs"]
    }


@app.get("/artikel")
def artikel_abrufen(
    region: str = Query(None),
    quelle: str = Query(None),
    tage:   int = Query(60),
    limit:  int = Query(3000),
    offset: int = Query(0)
):
    tage  = min(max(tage, 1), 180)
    limit = min(limit, 3000)

    # Nicht-kategorisierte Artikel (tags leer) werden nach 7 Tagen ausgeblendet,
    # bleiben aber in der Datenbank erhalten.
    # datum ist als TEXT gespeichert → Vergleich über TO_CHAR (gleiche Format-Darstellung)
    query = """
        SELECT * FROM artikel
        WHERE datum >= TO_CHAR(NOW() - (%s * INTERVAL '1 day'), 'YYYY-MM-DD HH24:MI:SS')
        AND NOT (
            (tags IS NULL OR tags = '')
            AND datum < TO_CHAR(NOW() - INTERVAL '7 days', 'YYYY-MM-DD HH24:MI:SS')
        )
    """
    params = [tage]

    if region:
        query += " AND region = %s"
        params.append(region)
    if quelle:
        query += " AND quelle = %s"
        params.append(quelle)

    query += " ORDER BY datum DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    conn = db_verbinden()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    return {
        "anzahl": len(rows),
        "artikel": [dict(row) for row in rows]
    }


@app.get("/artikel-hauptseite")
def artikel_hauptseite(limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0), days: int = Query(1, ge=1, le=30), response: Response = None):
    conn = db_verbinden()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("""
        SELECT id, hash, titel, link, quelle, typ, region, datum, gespeichert, tags, beschreibung
        FROM artikel
        WHERE datum >= TO_CHAR(NOW() - %s * INTERVAL '1 day', 'YYYY-MM-DD HH24:MI:SS')
        ORDER BY datum DESC
        LIMIT %s OFFSET %s
    """, (days, limit + 1, offset))
    rows = cursor.fetchall()
    hat_mehr = len(rows) > limit
    rows = rows[:limit]
    cursor.close()
    conn.close()
    if response:
        response.headers["Cache-Control"] = "public, max-age=60"
    return {"anzahl": len(rows), "hat_mehr": hat_mehr, "offset": offset, "artikel": [dict(r) for r in rows]}


@app.get("/archiv")
def archiv_abrufen(
    seite:  int = Query(1),
    limit:  int = Query(50),
    region: str = Query(None),
    suche:  str = Query(None),
    von:    str = Query(None),
    bis:    str = Query(None),
    response: Response = None,
):
    """Returns archived articles:
    - Unknown-region articles older than 7 days
    - Hessen/Osthessen articles older than 14 days
    """
    limit  = min(limit, 100)
    offset = (seite - 1) * limit

    base = """
        FROM artikel
        WHERE (
            (region IS NULL OR region NOT IN %s)
            AND datum < TO_CHAR(NOW() - INTERVAL '7 days', 'YYYY-MM-DD HH24:MI:SS')
        ) OR (
            region = ANY(%s)
            AND datum < TO_CHAR(NOW() - INTERVAL '14 days', 'YYYY-MM-DD HH24:MI:SS')
        )
    """
    # First two params are the region tuples used in the base WHERE clause
    params: list = [_ALLE_BEKANNTEN_SQL, list(REGIONEN_HESSEN)]

    extra = ""
    if region:
        extra += " AND region = %s"
        params.append(region)
    if suche:
        extra += " AND (titel ILIKE %s OR beschreibung ILIKE %s)"
        params.extend([f"%{suche}%", f"%{suche}%"])
    if von:
        extra += " AND datum >= %s"
        params.append(von)
    if bis:
        extra += " AND datum <= %s"
        params.append(bis + " 23:59:59")

    conn = db_verbinden()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute(f"SELECT COUNT(*) {base}{extra}", params)
    gesamt = cursor.fetchone()["count"]

    cursor.execute(
        f"SELECT id, titel, link, quelle, typ, region, datum, tags, beschreibung {base}{extra} ORDER BY datum DESC LIMIT %s OFFSET %s",
        params + [limit, offset]
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    import math
    if response:
        response.headers["Cache-Control"] = "public, max-age=300"
    return {
        "artikel":        [dict(r) for r in rows],
        "gesamt":         gesamt,
        "seite":          seite,
        "seiten_gesamt":  math.ceil(gesamt / limit) if gesamt else 1,
    }


@app.get("/ort-vollsuche")
def ort_vollsuche(region: str = Query(...), limit: int = Query(200, ge=1, le=500)):
    """Returns all articles matching a specific region/municipality across the entire database,
    without date restrictions. Used as fallback for villages with sparse recent content."""
    limit = min(limit, 500)
    conn = db_verbinden()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("""
        SELECT id, hash, titel, link, quelle, typ, region, datum, gespeichert, tags, beschreibung
        FROM artikel
        WHERE region = %s OR titel ILIKE %s OR tags ILIKE %s OR beschreibung ILIKE %s
        ORDER BY datum DESC
        LIMIT %s
    """, (region, f"%{region}%", f"%{region}%", f"%{region}%", limit))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"artikel": [dict(r) for r in rows], "anzahl": len(rows)}


@app.get("/artikel/{artikel_id}")
def einzelner_artikel(artikel_id: int):
    conn = db_verbinden()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT * FROM artikel WHERE id = %s", (artikel_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        return {"fehler": "Artikel nicht gefunden"}
    return dict(row)


@app.get("/quellen")
def quellen_abrufen():
    conn = db_verbinden()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("""
        SELECT quelle, region, typ, COUNT(*) as anzahl
        FROM artikel
        GROUP BY quelle, region, typ
        ORDER BY anzahl DESC
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    return {
        "anzahl": len(rows),
        "quellen": [dict(row) for row in rows]
    }


@app.get("/statistik")
def statistik():
    conn = db_verbinden()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM artikel")
    gesamt = cursor.fetchone()[0]

    cursor.execute("SELECT datum FROM artikel ORDER BY datum DESC LIMIT 1")
    neuester = cursor.fetchone()

    cursor.execute("SELECT datum FROM artikel ORDER BY datum ASC LIMIT 1")
    aeltester = cursor.fetchone()

    cursor.close()
    conn.close()

    return {
        "artikel_gesamt": gesamt,
        "neuester_artikel": neuester[0] if neuester else None,
        "aeltester_artikel": aeltester[0] if aeltester else None,
    }


@app.get("/push-public-key")
def push_public_key():
    return {"publicKey": os.getenv("VAPID_PUBLIC_KEY", "")}


@app.post("/push-abonnieren")
def push_abonnieren(abo: PushAbo):
    conn = db_verbinden()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO push_subscriptions (endpoint, p256dh, auth, heimat)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (endpoint) DO UPDATE SET heimat = EXCLUDED.heimat
    """, (abo.endpoint, abo.p256dh, abo.auth, abo.heimat))
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "ok"}


@app.patch("/push-abonnieren")
def push_heimat_aktualisieren(daten: PushHeimat):
    conn = db_verbinden()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE push_subscriptions SET heimat = %s WHERE endpoint = %s",
        (daten.heimat, daten.endpoint)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "ok"}


@app.delete("/push-abonnieren")
def push_abbestellen(daten: PushHeimat):
    conn = db_verbinden()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM push_subscriptions WHERE endpoint = %s", (daten.endpoint,))
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "ok"}


@app.post("/fcm-abonnieren")
def fcm_abonnieren(abo: FcmAbo):
    conn = db_verbinden()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO fcm_subscriptions (fcm_token, heimat)
        VALUES (%s, %s)
        ON CONFLICT (fcm_token) DO UPDATE SET heimat = EXCLUDED.heimat
    """, (abo.fcm_token, abo.heimat))
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "ok"}


@app.patch("/fcm-abonnieren")
def fcm_heimat_aktualisieren(abo: FcmAbo):
    conn = db_verbinden()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE fcm_subscriptions SET heimat = %s WHERE fcm_token = %s",
        (abo.heimat, abo.fcm_token)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "ok"}


@app.delete("/fcm-abonnieren")
def fcm_abbestellen(abo: FcmAbo):
    conn = db_verbinden()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM fcm_subscriptions WHERE fcm_token = %s", (abo.fcm_token,))
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "ok"}


def _aggregator_ausfuehren():
    from datetime import datetime, timedelta
    import fulda_news_aggregator as agg
    conn = agg.db_verbinden()
    agg.datenbank_einrichten(conn)
    agg._region_retroaktiv_korrigieren(conn)
    for feed in agg.FEEDS:
        agg.feed_verarbeiten(feed, conn)
    for quelle in agg.HTML_QUELLEN:
        agg.html_quelle_verarbeiten(quelle, conn)
    agg.deduplizieren(conn)
    agg.archiv_generieren(conn)
    agg.sitemap_generieren(conn)
    cutoff = (datetime.now() - timedelta(minutes=70)).strftime('%Y-%m-%d %H:%M:%S')
    agg.benachrichtigungen_senden(conn, cutoff)
    conn.close()


@app.patch("/artikel/{artikel_id}")
def artikel_bearbeiten(artikel_id: int, key: str, daten: dict):
    if key != os.getenv("AGGREGATOR_KEY"):
        raise HTTPException(status_code=403, detail="Ungültiger Schlüssel")
    erlaubte_felder = {"titel", "tags", "beschreibung"}
    felder = {k: v for k, v in daten.items() if k in erlaubte_felder}
    if not felder:
        raise HTTPException(status_code=400, detail="Keine gültigen Felder")
    set_clause = ", ".join(f"{k} = %s" for k in felder)
    conn = db_verbinden()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE artikel SET {set_clause} WHERE id = %s", [*felder.values(), artikel_id])
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "ok"}


@app.delete("/artikel/{artikel_id}")
def artikel_loeschen(artikel_id: int, key: str):
    if key != os.getenv("AGGREGATOR_KEY"):
        raise HTTPException(status_code=403, detail="Ungültiger Schlüssel")
    conn = db_verbinden()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM artikel WHERE id = %s", (artikel_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "gelöscht"}


@app.get("/aggregator-starten")
def aggregator_starten(key: str, background_tasks: BackgroundTasks):
    if key != os.getenv("AGGREGATOR_KEY"):
        raise HTTPException(status_code=403, detail="Ungültiger Schlüssel")
    background_tasks.add_task(_aggregator_ausfuehren)
    return {"status": "gestartet"}