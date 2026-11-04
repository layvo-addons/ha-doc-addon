# Änderungen

## 0.6.0
- Neu, optional und standardmässig aus: **Deckblatt-Angaben** (Ersteller/Firma, Kunde, Version/Stand, Bearbeiter) unter «Deckblatt: Ersteller und Kunde». Erscheinen auf dem Deckblatt der PDFs, auch im Monatsbericht; gespeichert in `share/ha_doc/cover.json`.

## 0.5.4
- Logo einstellbar: layvo-Logo, kein Logo oder ein eigenes Logo (PNG/JPG), unter «Logo im PDF» in der Oberfläche. Gilt für Deckblatt und Fusszeile; wird in `share/ha_doc/branding` gespeichert.
- Fusszeile der PDFs zeigt nur noch «Home Assistant Dokumentation» (der Standortname steht auf dem Deckblatt).

## 0.5.3
- Logo im Stil von layvo Studio (transparent, oben links auf dem Deckblatt, klein in der Fusszeile) und «Seite n / N».

## 0.5.2
- Das layvo-Logo steht auf dem Deckblatt der erzeugten PDFs.

## 0.5.1
- Neuer Name «layvo Doku» mit neuem Symbol und Logo.

## 0.5.0
- Eigene Bemerkungen: Knopf «Bemerkungen erfassen» öffnet eine Seite, auf der zu Bereichen, Geräten, Entitäten, Integrationen, Netzwerk-Clients, Automatisierungen, Skripten und Szenen (sowie allgemein) Text erfasst werden kann. Die Bemerkungen erscheinen im PDF, in der Excel-Datei (Spalte «Bemerkung») und im Änderungsvergleich.
- Die Bemerkungen liegen in `share/ha_doc/notes.json` und bleiben bei einer Neuinstallation erhalten.

## 0.4.0
- Optionaler Abschnitt «Änderungen seit letztem Stand»: vergleicht mit der letzten Momentaufnahme und zeigt neue, entfernte und geänderte Bereiche, Geräte, Entitäten, Integrationen, Automatisierungen, Skripte, Szenen und Netzwerk-Adressen (bei Automatisierungen mit Vorher/Nachher der Konfiguration).
- Momentaufnahmen liegen als JSON im Ordner `snapshots` (die letzten 24 werden behalten). Standardmässig aus.

## 0.3.2
- Dateien lassen sich in der Oberfläche einzeln löschen.
- Aufräumen (Anzahl aufbewahrter PDFs) betrifft nur noch automatisch erstellte Berichte (`ha_monatsbericht_…`); manuell erstellte Dateien bleiben, bis du sie löschst.

## 0.3.1
- Excel-Export: Geräteliste mit eingeklappten Entitäten (aufklappbar über die Gruppierung am linken Rand), dazu Blätter «Netzwerk» und «Integrationen».

## 0.3.0
- Neuer Abschnitt «Netzwerk»: IP, MAC, Hersteller, VLAN und WLAN/LAN der Geräte, gruppiert nach VLAN. Nur mit UniFi-Gateway oder Fritz!Box.
- Bei Geräten mit passender MAC-Adresse wird die IP in der Gerätetabelle angezeigt.

## 0.2.3
- Monatsbericht nutzt die in der Oberfläche gespeicherte Auswahl («Auswahl für Monatsbericht speichern»), inklusive Bereichen. Die Konfiguration dient als Ersatz.

## 0.2.2
- Konfiguration: Abschnitte des Monatsberichts sind jetzt einzelne Schalter statt einer Liste (die Liste liess sich nicht bearbeiten).

## 0.2.1
- Oberfläche folgt dem Dunkelmodus von Home Assistant.
- Monatsbericht: gleiche Filter wie in der Oberfläche (Diagnose-Entitäten, nur fehlende Entitäten, bestimmte Bereiche).

## 0.2.0
- Auswahl vor dem Erstellen: einzelne Bereiche, Diagnose-Entitäten ausblenden, nur Einträge mit fehlenden Entitäten.
- Monatlicher Bericht mit Aufbewahrung der letzten PDFs.
- Symbol, Logo, README und Übersetzungen.

## 0.1.6
- Blueprint-Automatisierungen: Name, Beschreibung und nur die vom Standard abweichenden Eingaben.
- Fehlende Entitäten in Blueprint-Eingaben werden gefunden.

## 0.1.5
- Automatisierungen als Schema (Auslöser → Bedingungen → Aktionen), auswählbar.

## 0.1.4
- Ein Kasten pro Gerät mit allen Entitäten und wiederholter Kopfzeile auf Folgeseiten.

## 0.1.3
- Gleichartige Auslöser werden zusammengefasst, uninteressante Dienste aus der Liste nicht verfügbarer Entitäten entfernt.
- Auswahl der Abschnitte vor dem Erstellen.

## 0.1.2
- Fehler behoben: Geräte mit sehr vielen Entitäten führten zu einem Abbruch beim Erstellen des PDFs.

## 0.1.1
- Aufbau des Images repariert (Python-Basisimage).

## 0.1.0
- Erste Version.
