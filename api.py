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
    """Neue Datenbankverbindung mit SSL-Parametern für Supabase."""
    return psycopg2.connect(
        os.getenv("DATABASE_URL"),
        connect_timeout=10,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )

def mit_retry(fn):
    """Führt fn(cursor) aus. Bei SSL-Fehler einmal neu verbinden und wiederholen."""
    for versuch in range(2):
        try:
            conn = db_verbinden()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            ergebnis = fn(cursor)
            cursor.close()
            conn.close()
            return ergebnis
        except psycopg2.OperationalError as e:
            if versuch == 1:
                raise
            # Erster Versuch fehlgeschlagen → sofort neu versuchen
            continue

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
    limit:  int = Query(50),
    offset: int = Query(0)
):
    limit = min(limit, 200)
    query = "SELECT * FROM artikel WHERE 1=1"
    params = []

    if region:
        query += " AND region = %s"
        params.append(region)
    if quelle:
        query += " AND quelle = %s"
        params.append(quelle)

    query += " ORDER BY datum DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    def ausfuehren(cursor):
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return {
            "anzahl": len(rows),
            "artikel": [dict(row) for row in rows]
        }

    return mit_retry(ausfuehren)


@app.get("/artikel/{artikel_id}")
def einzelner_artikel(artikel_id: int):
    def ausfuehren(cursor):
        cursor.execute("SELECT * FROM artikel WHERE id = %s", (artikel_id,))
        row = cursor.fetchone()
        if not row:
            return {"fehler": "Artikel nicht gefunden"}
        return dict(row)

    return mit_retry(ausfuehren)


@app.get("/quellen")
def quellen_abrufen():
    def ausfuehren(cursor):
        cursor.execute("""
            SELECT quelle, region, typ, COUNT(*) as anzahl
            FROM artikel
            GROUP BY quelle, region, typ
            ORDER BY anzahl DESC
        """)
        rows = cursor.fetchall()
        return {
            "anzahl": len(rows),
            "quellen": [dict(row) for row in rows]
        }

    return mit_retry(ausfuehren)


@app.get("/statistik")
def statistik():
    def ausfuehren(cursor):
        cursor.execute("SELECT COUNT(*) FROM artikel")
        gesamt = cursor.fetchone()["count"]

        cursor.execute("SELECT datum FROM artikel ORDER BY datum DESC LIMIT 1")
        neuester = cursor.fetchone()

        cursor.execute("SELECT datum FROM artikel ORDER BY datum ASC LIMIT 1")
        aeltester = cursor.fetchone()

        return {
            "artikel_gesamt": gesamt,
            "neuester_artikel": neuester["datum"] if neuester else None,
            "aeltester_artikel": aeltester["datum"] if aeltester else None,
        }

    return mit_retry(ausfuehren)