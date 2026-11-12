# Schach gegen Mensch – Anleitung für KIs

Mensch spielt Weiß mit der Maus, du spielst Schwarz nur über diese Terminal-Befehle:

1. `schach-brett "Dein Modellname"` – öffnet das Brett (oder holt es nach vorn). Oben steht „Mensch gegen <Name>“. Eine angefangene Partie wird automatisch weitergespielt.
2. Wenn Mensch sagt „du bist dran“: IMMER zuerst `schach-stellung` lesen (wer am Zug ist, letzter Zug, FEN, Textbrett, geschlagene Figuren, alle legalen Züge).
3. Dann `schach-zug e7e5` – Zug in UCI (z. B. e7e5, e8g8 für Rochade, a2a1q für Umwandlung) oder SAN (z. B. Nf6). Nur legale Züge, nur wenn Schwarz am Zug ist; sonst kommt eine Ablehnung mit der Liste legaler Züge.
4. `schach-neu` – neue Partie, nur wenn Mensch das will.

Ist das Brett zu, melden schach-stellung/schach-zug „Brett ist nicht offen – erst schach-brett“.
Jede Figur gleitet ca. 2 Sekunden über das Brett – Mensch sieht so jeden Zug.

## Brett einstellen (ab Version 5)
`schach-modus <spielart> [weiss|schwarz] [stufe] [--weiss "Name"] [--schwarz "Name"]`
- Spielarten: mensch-gegen-ki, mensch-gegen-stockfish, ki-gegen-stockfish, ki-gegen-ki
- Farbe gilt für den zuerst Genannten (Mensch bzw. die KI); Stufen: anfaenger, gelegenheit, verein, stark, meister, voll
- Beispiel: `schach-modus ki-gegen-stockfish weiss anfaenger`, danach `schach-neu`. Ohne Angaben: zeigt die aktuelle Einstellung.
