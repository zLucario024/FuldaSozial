# Nachrichtenquellen für den Landkreis Fulda: Vollständige Bestandsaufnahme

Der Landkreis Fulda verfügt über ein überraschend dichtes lokales Mediennetz – **über 80 identifizierte Quellen** verteilen sich auf Nachrichtenportale, Gemeinde-Websites, Amtsblätter, Social-Media-Kanäle und Behördenmeldungen. Die zentrale Erkenntnis: **Nur 8–10 Quellen bieten funktionierende RSS-Feeds**, während die Mehrheit der Gemeinden auf Apps (meinOrt, DorfFunk, eigene Gemeinde-Apps) statt auf RSS als digitalen Nachrichtenkanal setzt. Zwei Schlüsselakteure dominieren die lokale Medienlandschaft – die **Mediengruppe Parzeller** (Fuldaer Zeitung, Marktkorb, Wir lieben Fulda) und die **LINUS WITTICH Medien KG** (alle 23 Gemeindeblätter).

---

## 1. Verifizierte Nachrichtenportale und Zeitungen

### Quellen mit bestätigtem RSS-Feed

| Quelle | URL | RSS-Feed URL | Typ | Relevanz |
|--------|-----|-------------|-----|----------|
| **fuldainfo.de** | https://www.fuldainfo.de/ | `https://www.fuldainfo.de/feed` ✅ | Nachrichtenportal | Sehr hoch – ~74.700 FB-Likes, unabhängig |
| **hessenschau Osthessen** | https://www.hessenschau.de/osthessen/ | `https://www.hessenschau.de/osthessen/index.rss` ✅ | ÖR-Rundfunk (hr) | Sehr hoch – offiziell dokumentiert |
| **Presseportal Polizei Fulda** | https://www.presseportal.de/blaulicht/r/Fulda | `https://www.presseportal.de/rss/polizei/r/Fulda.rss2` ✅ | Polizeimeldungen | Sehr hoch |
| **Presseportal PP Osthessen** | https://www.presseportal.de/blaulicht/nr/43558 | `https://www.presseportal.de/rss/dienststelle_43558.rss2` ✅ | Polizeimeldungen | Sehr hoch – alle Blaulicht-Meldungen |
| **Osthessen-News** | https://osthessen-news.de/ | `https://osthessen-news.de/rss_feed.xml` ⚠️ | Nachrichtenportal | Sehr hoch – größtes Onlinemedium der Region |
| **Presseportal HS Fulda** | https://www.presseportal.de/nr/121509 | `https://www.presseportal.de/rss/pm_121509.rss2` ⚠️ | Hochschule | Hoch |

⚠️ = URL folgt dem Standard-Schema und ist plausibel, konnte aber nicht direkt als XML verifiziert werden.

### Quellen mit wahrscheinlichem WordPress-RSS-Feed (ungeprüft)

Diese Quellen basieren auf WordPress, das standardmäßig einen `/feed/`-Endpunkt generiert. Eine Verifizierung mit einem RSS-Reader wird empfohlen.

| Quelle | Mögliche RSS-Feed URL | Typ | Relevanz |
|--------|-----------------------|-----|----------|
| **Marktkorb** | `https://www.marktkorb.de/feed/` | Wochenblatt (Parzeller) | Hoch – 121.500 Auflage, 4 Lokalausgaben |
| **Wir lieben Fulda** | `https://www.wirliebenfulda.de/feed/` | Lifestyle-/Community-Portal | Mittel |
| **Kreisfeuerwehrverband Fulda** | `https://kfv-fulda.de/feed/` | Feuerwehr | Hoch |
| **Nüsttal Aktuell** | `https://www.nuesttal-aktuell.de/feed/` | Lokales Community-Portal | Mittel |

### Quellen ohne RSS-Feed

| Quelle | URL | Typ | Relevanz | Bemerkung |
|--------|-----|-----|----------|-----------|
| **Fuldaer Zeitung** | https://www.fuldaerzeitung.de/fulda/ | Tageszeitung (seit 1874) | Sehr hoch – einzige Tageszeitung | Paywall, kein öffentlicher RSS. Kopfblätter: Hünfelder Zeitung, Schlitzer Bote |
| **Osthessen-Zeitung** | https://www.osthessen-zeitung.de/ | Online-Nachrichtenportal | Sehr hoch – eigenständig neben Osthessen-News | Custom-CMS, kein RSS |
| **FFH Fulda** | https://www.ffh.de/nachrichten/orte/fulda.html | Radiosender | Mittel-hoch | Nur Podcast, kein Web-RSS für Fulda |
| **fuldaernachrichten.de** | https://www.fuldaernachrichten.de/ | — | — | **Domain nicht mehr erreichbar**, aus Liste entfernen |

### Hochschule Fulda – eigene RSS-Feeds

Die Hochschule Fulda bietet auf `https://www.hs-fulda.de/rss-feeds` eine Übersicht mehrerer RSS-Feeds, darunter Feeds für Neuigkeiten, Pressemitteilungen und einzelne Fachbereiche (Informatik, Elektrotechnik, Lebensmitteltechnologie, Oecotrophologie, Pflege & Gesundheit, Sozial- & Kulturwissenschaften). Der allgemeine News-Feed liegt vermutlich unter `https://www.hs-fulda.de/fileadmin/Fachbereiche/rss/news.xml` – eine direkte Verifizierung mit einem RSS-Reader ist empfohlen.

---

## 2. Alle 23 Gemeinde-Websites im Überblick

**Kein einziges der 23 Gemeinde-Websites bietet einen öffentlich beworbenen RSS-Feed.** Stattdessen setzen mehrere Gemeinden auf mobile Apps als modernen Ersatz. Alle Gemeinden haben jedoch aktuelle Nachrichtenbereiche auf ihren Websites.

| Gemeinde | Website | Aktuelles | Amtsblatt | App |
|----------|---------|-----------|-----------|-----|
| **Bad Salzschlirf** | https://www.badsalzschlirf.de/ | Startseite | — | — |
| **Burghaun** | https://www.burghaun.de/ | Startseite | — | — |
| **Dipperz** | https://www.dipperz.de/ | Startseite | — | — |
| **Ebersburg** | https://www.ebersburg.de/ | Startseite | — | — |
| **Ehrenberg (Rhön)** | https://ehrenberg-rhoen.de/ | /service/neuigkeiten/ | Öffentliche Bekanntmachungen | **Ehrenberg-App** |
| **Eichenzell** | https://www.eichenzell.de/de/ | Startseite | **Eichenzeller Nachrichten** (online) | — |
| **Eiterfeld** | https://www.eiterfeld.de/ | /neuigkeiten/ + /pressemitteilungen/ | **Digitales Blättchen** (E-Paper) | **meinOrt-App** |
| **Flieden** | https://www.flieden.de/ | /rathaus-politik/aktuelles/ | **Wochenblatt online** | — |
| **Fulda (Stadt)** | https://www.fulda.de/ | /news (umfangreich, 15+ Seiten) | Amtliche Bekanntmachungen | — |
| **Gersfeld (Rhön)** | https://www.gersfeld.de/ | Rathaus-Bereich | Gersfelder Rhönbote (Print) | — |
| **Großenlüder** | https://www.grossenlueder.de/ | /rathaus/aktuelle-nachrichten/ | **Lüdertalbote** (E-Paper) | **Bürger-App** |
| **Hilders** | https://www.hilders.de/ | Verteilt auf Unterseiten | **Blättchen** (online) | — |
| **Hofbieber** | https://www.hofbieber.de/ | /dorfleben/aktuelles | **Blickpunkt Hofbieber** (Wittich) | **meinOrt-App** |
| **Hosenfeld** | https://www.gemeinde-hosenfeld.de/ | Startseite | Amtliche Bekanntmachungen | — |
| **Hünfeld (Stadt)** | https://www.huenfeld.de/de/ | Umfangreicher News-Bereich | Amtliche Bekanntmachungen | **App „Hünfeld – meine Stadt"** |
| **Kalbach** | https://www.gemeinde-kalbach.de/ | /aktuelles-aus-dem-rathaus | Amtliche Bekanntmachungen | **meinOrt-App** |
| **Künzell** | https://www.kuenzell.de/ | /aktuelles/ | **Online-Amtsblatt** (extern verlinkt) | — |
| **Neuhof** | https://www.neuhof-fulda.de/ | /aktuelle-pressemitteilungen/ | **Neuhofer Rundschau** | — |
| **Nüsttal** | https://www.nuesttal.de/ | Startseite | Amtliche Bekanntmachungen | **DorfFunk-App** |
| **Petersberg** | https://petersberg.de/ | Startseite (sehr aktiv) | **Blickpunkt Petersberg** (E-Paper) | KI-Chatbot „Charly" |
| **Poppenhausen** | https://www.poppenhausen-wasserkuppe.de/ | Startseite | — | — |
| **Rasdorf** | https://www.rasdorf.de/ | Startseite | — | — |
| **Tann (Rhön)** | https://tann-rhoen.de/ | Startseite | Amtliche Bekanntmachungen | — |

Drei Gemeinden stechen besonders hervor: **Petersberg** (KI-Chatbot, Digital-Award, Gemeindezeitung seit 1979), **Hünfeld** (umfangreichster Nachrichtenbereich, Smart-City-Projekt) und **Nüsttal** (Digitale-Dörfer-Projekt mit DorfFunk-App plus das eigenständige Portal https://www.nuesttal-aktuell.de/).

Zusätzlich existiert für Petersberg ein eigenständiges lokales Nachrichtenportal: **https://www.petersberg-aktuell.de/** (Teil des Osthessen-Zeitung-Netzwerks) und für Poppenhausen das Community-Portal **http://www.poppenhausen-aktiv.de/** (Nachrichten von Vereinen, Feuerwehr, Schule).

---

## 3. Amtsblätter und Mitteilungsblätter

Der mit Abstand wichtigste Akteur für die amtlichen Mitteilungsblätter im Landkreis Fulda ist die **LINUS WITTICH Medien KG** (Sitz: Herbstein). Der Verlag produziert und verteilt **wöchentlich kostenlose Mitteilungsblätter an alle Haushalte** sämtlicher 23 Gemeinden.

**Zentrale Online-Plattform:** https://ol.wittich.de – hier können alle Gemeindeblätter als E-Paper gelesen werden. Kein RSS-Feed verfügbar.

Namentlich bekannte Blätter mit Online-Zugang:

- **Blickpunkt Petersberg** / Gemeindezeitung: https://www.wittich.de/produkte/zeitungen/1142-amtsblatt-blickpunkt-petersberg
- **Künzell – Aus dem Leben der Gemeinde**: https://www.wittich.de/produkte/zeitungen/1092-kuenzell-aus-dem-leben-der-gemeinde
- **Eichenzeller Nachrichten**: https://www.eichenzell.de/de/buergerservice-rathaus/eichenzeller-nachrichten/
- **Blickpunkt Hofbieber**: Herausgeber LINUS WITTICH
- **Lüdertalbote** (Großenlüder): https://www.grossenlueder.de/rathaus-buergerservice/rathaus/luedertalbote/
- **Neuhofer Rundschau**: Im Navigationsmenü von neuhof-fulda.de
- **Blättchen** (Hilders): https://www.hilders.de/rathaus/buergerservice/online-rathaus/blaettchen
- **Digitales Blättchen** (Eiterfeld): Über meinOrt-App
- **Wochenblatt online** (Flieden): https://www.flieden.de/rathaus-politik/buergerservice/wochenblatt-online/

Weitere amtliche Quellen:
- **Landkreis Fulda – Amtliche Bekanntmachungen**: https://www.landkreis-fulda.de/amtliche-bekanntmachungen
- **Stadt Fulda – Amtliche Bekanntmachungen**: https://www.fulda.de/stadt-politik/information/amtliche-bekanntmachungen
- **Kirchliches Amtsblatt Bistum Fulda**: https://www.bistum-fulda.de/bistum_fulda/bistum/recht/amtsblatt/

---

## 4. Polizei, Feuerwehr und Behördenmeldungen

Das **Polizeipräsidium Osthessen** (Sitz: Severingstraße 1-7, 36041 Fulda) ist die zentrale Quelle für Blaulichtmeldungen. Es betreut die Landkreise Fulda, Hersfeld-Rotenburg und Vogelsberg und ist auf allen relevanten Kanälen präsent:

| Kanal | URL | RSS |
|-------|-----|-----|
| **Presseportal (Dienststelle)** | https://www.presseportal.de/blaulicht/nr/43558 | `https://www.presseportal.de/rss/dienststelle_43558.rss2` ✅ |
| **Presseportal (Region Fulda)** | https://www.presseportal.de/blaulicht/r/Fulda | `https://www.presseportal.de/rss/polizei/r/Fulda.rss2` ✅ |
| **Website PP Osthessen** | https://ppoh.polizei.hessen.de/ | — |
| **Facebook** | https://www.facebook.com/PolizeiOsthessen/ | — (~5.260 Likes) |
| **Instagram** | https://www.instagram.com/polizei_oh/ | — (~13.000 Follower) |
| **X (Twitter)** | https://x.com/polizei_oh | — |
| **YouTube** | https://www.youtube.com/channel/UCUGcNYNkgEozGyLACRu7Khw | — |

Feuerwehr-Quellen:
- **Kreisfeuerwehrverband Fulda**: https://kfv-fulda.de/ (WordPress, möglicher RSS: `/feed/`) – betreut 161 Freiwillige Feuerwehren
- **Feuerwehr der Stadt Fulda**: https://www.fulda.de/buergerservice/feuerwehr-der-stadt-fulda/
- **Facebook Feuerwehr Fulda**: https://www.facebook.com/feuerwehrfulda/ (~3.570 Likes)
- **Facebook KFV Fulda**: https://www.facebook.com/kfv.fulda/
- **Instagram Feuerwehr Fulda**: https://www.instagram.com/feuerwehr.fulda/ (~3.350 Follower)

Der **Landkreis Fulda** selbst veröffentlicht Pressemitteilungen unter https://www.landkreis-fulda.de/buergerservice/pressemitteilungen (kein RSS). Die alte URL `https://neu.landkreis-fulda.de/rss-feed` ist **nicht mehr erreichbar** und sollte aus der Quellenliste entfernt werden.

---

## 5. Social Media, Facebook-Gruppen und Community-Kanäle

### Instagram – Die wichtigsten Accounts

| Account | Handle | Follower | Typ |
|---------|--------|----------|-----|
| **Fulda.Stadt.Leben** (Tourist-Info) | @fulda.stadt.leben | ~16.000 | Offiziell |
| **Wir lieben Fulda** | @wirliebenfulda | ~14.000 | Community |
| **Polizei Osthessen** | @polizei_oh | ~13.000 | Behörde |
| **Fulda.deineBauern** | @fulda.deinebauern | ~4.200 | Landwirtschaft |
| **Landkreis Fulda** | @landkreisfulda | ~3.700 | Offiziell |
| **Feuerwehr Fulda** | @feuerwehr.fulda | ~3.350 | Behörde |
| **Fulda Aktuell** (Wochenzeitung) | @fulda_aktuell | ~2.600 | Medien |
| **Osthessen-Zeitung** | — | ~17.000 | Medien |

### Facebook – Seiten und Gruppen

Die reichweitenstärksten Facebook-Seiten sind **fuldainfo** (~74.700 Likes), **Fuldaer Zeitung** (~35.100 Likes), **Osthessen-News** (85.527 Follower) und **Stadt Fulda** (~8.900 Likes). Relevante Facebook-Gruppen umfassen „Kaufen, Verkaufen & Verschenken in Fulda/Osthessen" (https://www.facebook.com/groups/Fuldaer.Marktplatz/), „Fulda wie es früher mal war" (https://www.facebook.com/groups/217701638436561/) und die fuldainfo.de-Gruppe (https://www.facebook.com/groups/171763869560791/).

### Messenger-Kanäle

**fuldainfo.de** betreibt einen aktiven **WhatsApp-Kanal** mit täglicher Nachrichtenübersicht (Link über https://www.fuldainfo.de/). Weitere öffentliche Telegram- oder WhatsApp-Gruppen für allgemeine Lokalnachrichten sind kaum auffindbar, da diese meist geschlossen und nicht indexiert sind.

---

## 6. Kirche, Wirtschaft, Rhön und Sport

### Kirchliche Quellen
Das **Bistum Fulda** veröffentlicht aktuelle Meldungen unter https://www.bistum-fulda.de/bistum_fulda/presse_medien/aktuelle_meldungen.php. Auf der Website wird ein RSS-Feed erwähnt, die exakte URL konnte jedoch nicht verifiziert werden. Die Facebook-Seite des Bistums: https://www.facebook.com/BistumFuldaNews/.

### Wirtschaft
Die **IHK Fulda** publiziert Pressemeldungen unter https://www.ihk.de/fulda/presse (kein RSS). Das IHK-Magazin **„Wirtschaft Region Fulda"** erscheint 6x jährlich mit ~13.000 Auflage und ist als **Podcast auf Spotify** verfügbar: https://open.spotify.com/show/29CeCEyCTOy0OEO5I0ePm4. Die Wirtschaftsförderung betreibt einen Blog unter https://www.region-fulda.de/en/blog/.

### Rhön-spezifische Quellen
Das **UNESCO-Biosphärenreservat Rhön** (hessische Verwaltung mit Sitz in Hilders, also direkt im Landkreis Fulda) veröffentlicht ein Newsarchiv unter https://www.biosphaerenreservat-rhoen.de/service/newsarchiv (kein RSS). Die **Rhön- und Saalepost** (https://www.rhoenundsaalepost.de/) berichtet primär über die bayerische Rhön, ist aber für grenzüberschreitende Themen relevant. Weitere Rhön-Portale wie https://www.rhoenfuehrer.de/ bieten Veranstaltungskalender.

### Sport
Die **SG Barockstadt Fulda-Lehnerz** (Regionalliga Südwest, 4. Liga) ist der größte Fußballverein der Region: https://sg-barockstadt.de/ (WordPress, möglicher RSS unter `/feed/`). Überregionale Berichterstattung läuft über https://www.torgranate.de/regionalliga/sg-barockstadt-org1524234/.

### Veranstaltungen
Das Portal **Spüre Fulda** (https://spuere-fulda.de/) und die Facebook-Seite **Feste & Events in Fulda** (https://www.facebook.com/fuldaevents/, ~2.680 Likes) aggregieren Veranstaltungen. Für 2026 besonders relevant: der **Hessentag in Fulda** mit eigener Website https://hessentag-fulda.de/.

---

## 7. Zusammenfassung: Alle bestätigten RSS-Feeds

Die folgende Tabelle enthält alle Quellen mit funktionierenden oder sehr wahrscheinlich funktionierenden RSS-Feeds, sortiert nach Zuverlässigkeit:

| # | Quelle | RSS-Feed URL | Status |
|---|--------|-------------|--------|
| 1 | **fuldainfo.de** | `https://www.fuldainfo.de/feed` | ✅ Aktiv bestätigt |
| 2 | **hessenschau Osthessen** | `https://www.hessenschau.de/osthessen/index.rss` | ✅ Offiziell dokumentiert |
| 3 | **Presseportal Polizei Fulda** | `https://www.presseportal.de/rss/polizei/r/Fulda.rss2` | ✅ Bestätigt |
| 4 | **Presseportal PP Osthessen** | `https://www.presseportal.de/rss/dienststelle_43558.rss2` | ✅ Bestätigt |
| 5 | **Osthessen-News** | `https://osthessen-news.de/rss_feed.xml` | ⚠️ Plausibel |
| 6 | **Hochschule Fulda** | Mehrere Feeds via `https://www.hs-fulda.de/rss-feeds` | ⚠️ Übersichtsseite bestätigt |
| 7 | **Presseportal HS Fulda** | `https://www.presseportal.de/rss/pm_121509.rss2` | ⚠️ Schema-konform |
| 8 | **Marktkorb** | `https://www.marktkorb.de/feed/` | ⚠️ WordPress-Standard |
| 9 | **Wir lieben Fulda** | `https://www.wirliebenfulda.de/feed/` | ⚠️ WordPress-Standard |
| 10 | **KFV Fulda** | `https://kfv-fulda.de/feed/` | ⚠️ WordPress-Standard |
| 11 | **Nüsttal Aktuell** | `https://www.nuesttal-aktuell.de/feed/` | ⚠️ WordPress-Standard |

**Zu entfernen:**
- `https://www.fuldaernachrichten.de/?feed=rss2` → Domain nicht mehr erreichbar

---

## Schlussfolgerungen und Empfehlungen

Die Recherche offenbart ein **klares Zwei-Klassen-System**: Wenige große Portale (Osthessen-News, fuldainfo.de, Fuldaer Zeitung) dominieren die digitale Nachrichtenlandschaft, während die 23 Gemeinden überwiegend auf **analoge oder App-basierte Kanäle** setzen. RSS-Feeds sind die Ausnahme, nicht die Regel. Wer eine vollständige Abdeckung des Landkreises erreichen will, muss drei Strategien kombinieren: die bestätigten RSS-Feeds einbinden, die WordPress-Feeds testen und aktivieren, sowie für RSS-lose Quellen (insbesondere die Gemeinde-Websites, Osthessen-Zeitung und Fuldaer Zeitung) auf Web-Scraping oder API-Abfragen ausweichen.

Ein besonders ergiebiger, bisher ungenutzter Kanal ist die **LINUS WITTICH-Plattform** (ol.wittich.de), die sämtliche 23 Gemeindeblätter digital vorhält – allerdings ohne RSS oder API. Die **Presseportal-RSS-Feeds** sind die zuverlässigste Quelle für Blaulichtmeldungen und sollten beide parallel genutzt werden (regionaler Feed + Dienststellen-Feed), da sie sich ergänzen. Schließlich verdient die **Hochschule Fulda** besondere Beachtung als einzige Institution, die aktiv eine strukturierte RSS-Feed-Übersichtsseite mit mehreren thematischen Feeds betreibt.