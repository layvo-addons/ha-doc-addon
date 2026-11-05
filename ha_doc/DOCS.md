# layvo Doku

Seitenleiste → **layvo Doku** → Abschnitte und Optionen wählen → **PDF erstellen**.
Die PDFs liegen in der Freigabe `share`, Ordner `ha_doc`.

## Optionen im PDF

- **Abschnitte:** Übersicht, Bereiche und Geräte, Integrationen, Automatisierungen (Text und/oder Schema), Skripte, Szenen, Helfer, Auffälligkeiten.
- **Bereiche auswählen:** nur einzelne Bereiche dokumentieren.
- **Konfigurations-/Diagnose-Entitäten ausblenden:** kürzere Geräteliste.
- **Nur Einträge mit fehlenden Entitäten:** zeigt Automatisierungen, Skripte und Szenen, die auf nicht mehr vorhandene Entitäten verweisen.

## Monatsbericht

Klicke in «layvo Doku» auf **Einstellungen Monatsbericht**. Auf der Seite stellst du ein:

- **Zeitplan:** Automatik ein/aus (Standard: aus), Tag im Monat (1–28), Uhrzeit `HH:MM` (Zeitzone von Home Assistant), Anzahl aufbewahrter automatischer Berichte (ältere werden gelöscht; manuell erstellte Dateien nie, sie löschst du in der Oberfläche).
- **Abschnitte** und **Optionen** (Diagnose-Entitäten ausblenden, nur fehlende Entitäten) sowie **Bereiche**, wie auf der Hauptseite.

Änderungen gelten sofort, ein Neustart ist nicht nötig. Das Add-on muss laufen («Beim Systemstart starten»). Die Einstellungen liegen in `share/ha_doc/schedule.json`. Die Konfiguration des Add-ons enthält keine Optionen mehr.


**Deckblatt:** Unter «Deckblatt: Ersteller und Kunde» kannst du optional Firma (Ersteller) und Kunde mit Adresse sowie Version/Stand und Bearbeiter erfassen. Mit dem Haken «Angaben auf dem Deckblatt anzeigen» erscheinen sie auf dem Deckblatt (auch im Monatsbericht). Standardmässig ist das aus. Die Angaben liegen in `share/ha_doc/cover.json`. Du bist für Weitergabe und Datenschutz der PDFs selbst verantwortlich.

**Logo:** Unter «Logo im PDF» wählst du das layvo-Logo, kein Logo oder ein eigenes Logo (PNG oder JPG, höchstens 2 MB). Das Logo steht auf dem Deckblatt und klein in der Fusszeile der PDFs. Die Einstellung liegt in `share/ha_doc/branding` und bleibt bei einer Neuinstallation erhalten.

Das Add-on muss laufen, schalte dafür **Beim Systemstart starten** ein.
