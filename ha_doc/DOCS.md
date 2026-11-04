# layvo Doku

Seitenleiste → **layvo Doku** → Abschnitte und Optionen wählen → **PDF erstellen**.
Die PDFs liegen in der Freigabe `share`, Ordner `ha_doc`.

## Optionen im PDF

- **Abschnitte:** Übersicht, Bereiche und Geräte, Integrationen, Automatisierungen (Text und/oder Schema), Skripte, Szenen, Helfer, Auffälligkeiten.
- **Bereiche auswählen:** nur einzelne Bereiche dokumentieren.
- **Konfigurations-/Diagnose-Entitäten ausblenden:** kürzere Geräteliste.
- **Nur Einträge mit fehlenden Entitäten:** zeigt Automatisierungen, Skripte und Szenen, die auf nicht mehr vorhandene Entitäten verweisen.

## Konfiguration (Monatsbericht)

Der Monatsbericht nutzt standardmässig die Auswahl der Oberfläche: Wähle in «layvo Doku» Abschnitte und Filter und klicke auf **Auswahl für Monatsbericht speichern**. Ist nichts gespeichert oder `schedule_from_ui` aus, gelten diese Optionen:

| Option | Bedeutung |
|---|---|
| schedule_enabled | Monatlichen Bericht automatisch erstellen |
| schedule_day | Tag im Monat (1–28) |
| schedule_time | Uhrzeit `HH:MM` (Zeitzone von Home Assistant) |
| keep_last | Anzahl aufbewahrter automatischer Berichte (ältere werden gelöscht; manuell erstellte Dateien nie, sie löschst du in der Oberfläche) |
| schedule_from_ui | Auswahl der Oberfläche für den Monatsbericht verwenden (Standard: an) |
| schedule_uebersicht … schedule_auffaelligkeiten | Ein Schalter pro Abschnitt im Bericht (Standard: alle an) |
| schedule_hide_diagnostic | Konfigurations-/Diagnose-Entitäten ausblenden (Standard: ja) |
| schedule_only_problems | Nur Einträge mit fehlenden Entitäten |
| schedule_areas | Nur diese Bereiche (Namen); leer = alle |

Die Abschnitte: `uebersicht`, `bereiche`, `integrationen`, `netzwerk`, `automatisierungen` (Text), `schema` (Automatisierungen als Schema), `skripte`, `szenen`, `helfer`, `auffaelligkeiten`.

**Netzwerk:** Der Abschnitt «Netzwerk» zeigt IP, MAC, Hersteller, VLAN und WLAN/LAN der Geräte im Heimnetz und ergänzt bei Geräten die IP-Adresse. Er funktioniert **nur mit der Integration «UniFi Network» (UniFi-Gateway) oder «AVM FRITZ!Box Tools» (Fritz!Box)**. Bei anderen Routern bleibt er leer. Bei UniFi müssen unter «Konfigurieren» die Netzwerk-Clients verfolgt werden.

**Excel:** Der Knopf «Excel erstellen» legt eine .xlsx-Datei an. Im Blatt «Geräte» sind die Entitäten zunächst eingeklappt: mit dem Plus am linken Rand (oder den Ebenen-Knöpfen 1/2 oben links) klappst du sie auf und zu. Bereiche und der Diagnose-Filter der Oberfläche gelten auch hier.

**Änderungen (optional):** Der Abschnitt «Änderungen seit letztem Stand» ist standardmässig aus. Wählst du ihn, vergleicht das PDF den aktuellen Stand mit der letzten gespeicherten Momentaufnahme (JSON im Ordner `snapshots`). Automatische Berichte speichern jedes Mal einen neuen Stand, manuelle Berichte nur mit der Option «diesen Stand als neue Referenz speichern» (der allererste Lauf speichert immer). Der Vergleich zeigt, **was** sich geändert hat, nicht **wer** es geändert hat. Home Assistant speichert das meist nicht.

**Bemerkungen:** Mit dem Knopf «Bemerkungen erfassen» öffnest du eine Seite mit aufklappbaren Bereichen und Geräten (Plus-Zeichen). Dort kannst du zu Bereichen, Geräten, Entitäten, Integrationen, Netzwerk-Clients, Automatisierungen, Skripten und Szenen einen Text erfassen, dazu eine allgemeine Bemerkung für das Deckblatt. Sie erscheinen im PDF (gelb hinterlegt), in der Excel-Datei und im Änderungsvergleich. Gespeichert wird in `share/ha_doc/notes.json`.

**Deckblatt:** Unter «Deckblatt: Ersteller und Kunde» kannst du optional Firma (Ersteller) und Kunde mit Adresse sowie Version/Stand und Bearbeiter erfassen. Mit dem Haken «Angaben auf dem Deckblatt anzeigen» erscheinen sie auf dem Deckblatt (auch im Monatsbericht). Standardmässig ist das aus. Die Angaben liegen in `share/ha_doc/cover.json`. Du bist für Weitergabe und Datenschutz der PDFs selbst verantwortlich.

**Logo:** Unter «Logo im PDF» wählst du das layvo-Logo, kein Logo oder ein eigenes Logo (PNG oder JPG, höchstens 2 MB). Das Logo steht auf dem Deckblatt und klein in der Fusszeile der PDFs. Die Einstellung liegt in `share/ha_doc/branding` und bleibt bei einer Neuinstallation erhalten.

Das Add-on muss laufen, schalte dafür **Beim Systemstart starten** ein.
