"""
Fulda News API
==============
Stellt die gespeicherten Artikel aus der Datenbank als API bereit.

Starten:
    uvicorn api:app --reload
"""

import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, Query, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(
    title="Fulda News API",
    description="Regionale Nachrichten aus dem Landkreis Fulda",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

def db_verbinden():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    return conn


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


def _aggregator_ausfuehren():
    import fulda_news_aggregator as agg
    conn = agg.db_verbinden()
    agg.datenbank_einrichten(conn)
    for feed in agg.FEEDS:
        agg.feed_verarbeiten(feed, conn)
    for quelle in agg.HTML_QUELLEN:
        agg.html_quelle_verarbeiten(quelle, conn)
    agg.deduplizieren(conn)
    agg.sitemap_generieren(conn)
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