"""
Fulda News API
==============
Stellt die gespeicherten Artikel aus der Datenbank als API bereit.

Installation:
    pip install fastapi uvicorn

Starten:
    uvicorn api:app --reload

Dann im Browser öffnen:
    http://localhost:8000
    http://localhost:8000/artikel
    http://localhost:8000/docs
"""

import sqlite3
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

DB_DATEI = "fulda_news.db"

app = FastAPI(
    title="Fulda News API",
    description="Regionale Nachrichten aus dem Landkreis Fulda",
    version="1.0.0"
)

# Erlaubt später der Website, die API abzufragen
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# HILFSFUNKTION
# ─────────────────────────────────────────────

def db_verbinden():
    conn = sqlite3.connect(DB_DATEI)
    conn.row_factory = sqlite3.Row  # Gibt Zeilen als Dictionary zurück
    return conn

# ─────────────────────────────────────────────
# ENDPUNKTE
# ─────────────────────────────────────────────

@app.get("/")
def startseite():
    """Willkommensnachricht – zeigt ob die API läuft."""
    return {
        "status": "aktiv",
        "name": "Fulda News API",
        "endpunkte": ["/artikel", "/quellen", "/docs"]
    }


@app.get("/artikel")
def artikel_abrufen(
    region: str = Query(None, description="z.B. landkreis-fulda"),
    quelle: str = Query(None, description="z.B. Hessenschau Osthessen"),
    limit:  int = Query(50,   description="Anzahl Artikel (max. 200)"),
    offset: int = Query(0,    description="Ab welchem Artikel starten")
):
    """
    Gibt Artikel chronologisch zurück – neueste zuerst.
    Optional filterbar nach Region und Quelle.
    """
    limit = min(limit, 200)  # Maximal 200 auf einmal

    query = "SELECT * FROM artikel WHERE 1=1"
    params = []

    if region:
        query += " AND region = ?"
        params.append(region)

    if quelle:
        query += " AND quelle = ?"
        params.append(quelle)

    query += " ORDER BY datum DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    conn = db_verbinden()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return {
        "anzahl": len(rows),
        "artikel": [dict(row) for row in rows]
    }


@app.get("/artikel/{artikel_id}")
def einzelner_artikel(artikel_id: int):
    """Gibt einen einzelnen Artikel anhand seiner ID zurück."""
    conn = db_verbinden()
    row = conn.execute(
        "SELECT * FROM artikel WHERE id = ?", (artikel_id,)
    ).fetchone()
    conn.close()

    if not row:
        return {"fehler": "Artikel nicht gefunden"}

    return dict(row)


@app.get("/quellen")
def quellen_abrufen():
    """Gibt alle verfügbaren Quellen mit Artikelanzahl zurück."""
    conn = db_verbinden()
    rows = conn.execute("""
        SELECT quelle, region, typ, COUNT(*) as anzahl
        FROM artikel
        GROUP BY quelle
        ORDER BY anzahl DESC
    """).fetchall()
    conn.close()

    return {
        "anzahl": len(rows),
        "quellen": [dict(row) for row in rows]
    }


@app.get("/statistik")
def statistik():
    """Zeigt allgemeine Statistiken über die gesammelten Daten."""
    conn = db_verbinden()

    gesamt = conn.execute("SELECT COUNT(*) FROM artikel").fetchone()[0]
    neuester = conn.execute(
        "SELECT datum FROM artikel ORDER BY datum DESC LIMIT 1"
    ).fetchone()
    aeltester = conn.execute(
        "SELECT datum FROM artikel ORDER BY datum ASC LIMIT 1"
    ).fetchone()

    conn.close()

    return {
        "artikel_gesamt": gesamt,
        "neuester_artikel": neuester[0] if neuester else None,
        "aeltester_artikel": aeltester[0] if aeltester else None,
    }