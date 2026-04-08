"""
Tags Nachholen
==============
Einmaliges Script das Tags für alle bestehenden Artikel generiert.

Ausführen:
    python tags_nachholen.py
"""

import sqlite3
import anthropic
import os
from dotenv import load_dotenv

load_dotenv()

DB_DATEI = "fulda_news.db"

def tags_generieren(client, titel_liste):
    titel_text = "\n".join(
        f"{i+1}. {titel}" for i, titel in enumerate(titel_liste)
    )

    prompt = f"""Du bist ein Redakteur für regionale Nachrichten aus Hessen.
Generiere für jeden Artikel-Titel genau 3-5 kurze deutsche Schlagwörter.
Fokus auf: Ort, Thema, beteiligte Personen oder Institutionen.
Trenne die Tags mit " · ".
Antworte NUR mit den Tags, eine Zeile pro Artikel, keine Nummerierung.

Titel:
{titel_text}"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    zeilen = message.content[0].text.strip().split("\n")
    ergebnis = {}
    for i, titel in enumerate(titel_liste):
        if i < len(zeilen):
            ergebnis[titel] = zeilen[i].strip()
    return ergebnis


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("FEHLER: Kein API-Schlüssel in .env gefunden")
        return

    client = anthropic.Anthropic(api_key=api_key)
    conn = sqlite3.connect(DB_DATEI)

    artikel = conn.execute(
        "SELECT hash, titel FROM artikel WHERE tags IS NULL OR tags = ''"
    ).fetchall()

    print(f"{len(artikel)} Artikel ohne Tags gefunden")

    if not artikel:
        print("Alle Artikel haben bereits Tags!")
        conn.close()
        return

    batch_groesse = 20
    gesamt = len(artikel)

    for i in range(0, gesamt, batch_groesse):
        batch = artikel[i:i + batch_groesse]
        titel_liste = [titel for _, titel in batch]

        try:
            tags_dict = tags_generieren(client, titel_liste)

            for hash_wert, titel in batch:
                tags = tags_dict.get(titel, "")
                if tags:
                    conn.execute(
                        "UPDATE artikel SET tags = ? WHERE hash = ?",
                        (tags, hash_wert)
                    )
            conn.commit()

            fertig = min(i + batch_groesse, gesamt)
            print(f"Batch fertig: {fertig}/{gesamt} Artikel")

            # Beispiel-Tags anzeigen
            for _, titel in batch[:2]:
                tags = tags_dict.get(titel, "")
                print(f"  {titel[:60]}...")
                print(f"  Tags: {tags}")

        except Exception as e:
            print(f"FEHLER bei Batch {i//batch_groesse + 1}: {e}")

    print("\nFertig! Alle Tags gespeichert.")
    conn.close()


if __name__ == "__main__":
    main()