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
from fastapi import FastAPI, Query
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