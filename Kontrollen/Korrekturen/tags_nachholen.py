"""
Tags Nachholen
==============
Einmaliges Script das Tags für alle bestehenden Artikel generiert.

Ausführen:
    python tags_nachholen.py
"""

import psycopg2
import anthropic
import os
from dotenv import load_dotenv

load_dotenv()


def tags_generieren(client, titel_liste, beschreibung_liste=None):
    if beschreibung_liste is None:
        beschreibung_liste = [""] * len(titel_liste)

    titel_text = "\n".join(
        f"{i+1}. {titel}" + (f"\n   Kontext: {beschreibung_liste[i]}" if beschreibung_liste[i] else "")
        for i, titel in enumerate(titel_liste)
    )

    prompt = f"""Du bist ein Redakteur für regionale Nachrichten aus dem Landkreis Fulda in Hessen.
Generiere für jeden Artikel-Titel genau 3-5 kurze deutsche Schlagwörter.
Fokus auf: Ort, Thema, beteiligte Personen oder Institutionen.
Trenne die Tags mit " · ".
Antworte NUR mit den Tags, eine Zeile pro Artikel, keine Nummerierung, keine Leerzeilen.

Titel:
{titel_text}"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    zeilen = [z.strip() for z in message.content[0].text.strip().split("\n") if z.strip()]
    ergebnis = {}
    for i, titel in enumerate(titel_liste):
        if i < len(zeilen):
            ergebnis[titel] = zeilen[i]
    return ergebnis


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("FEHLER: Kein API-Schlüssel in .env gefunden")
        return

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("FEHLER: Kein DATABASE_URL in .env gefunden")
        return

    client = anthropic.Anthropic(api_key=api_key)
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT hash, titel, beschreibung FROM artikel WHERE tags IS NULL OR tags = ''"
    )
    artikel = cursor.fetchall()

    print(f"{len(artikel)} Artikel ohne Tags gefunden")

    if not artikel:
        print("Alle Artikel haben bereits Tags!")
        cursor.close()
        conn.close()
        return

    batch_groesse = 20
    gesamt = len(artikel)

    for i in range(0, gesamt, batch_groesse):
        batch = artikel[i:i + batch_groesse]
        titel_liste = [titel for _, titel, _ in batch]
        beschreibung_liste = [beschreibung or "" for _, _, beschreibung in batch]

        try:
            tags_dict = tags_generieren(client, titel_liste, beschreibung_liste)

            for hash_wert, titel, _ in batch:
                tags = tags_dict.get(titel, "")
                if tags:
                    cursor.execute(
                        "UPDATE artikel SET tags = %s WHERE hash = %s",
                        (tags, hash_wert)
                    )
            conn.commit()

            fertig = min(i + batch_groesse, gesamt)
            print(f"Batch fertig: {fertig}/{gesamt} Artikel")

            for _, titel, _ in batch[:2]:
                tags = tags_dict.get(titel, "")
                print(f"  {titel[:60]}...")
                print(f"  Tags: {tags}")

        except Exception as e:
            conn.rollback()
            print(f"FEHLER bei Batch {i//batch_groesse + 1}: {e}")

    print("\nFertig! Alle Tags gespeichert.")
    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
