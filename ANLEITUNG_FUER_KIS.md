# Schach gegen Spieler – Anleitung für KIs

Spieler spielt Weiß mit der Maus, du spielst Schwarz nur über diese Terminal-Befehle:

1. `schach-brett "Dein Modellname"` – öffnet das Brett (oder holt es nach vorn). Oben steht „Spieler gegen <Name>“. Eine angefangene Partie wird automatisch weitergespielt.
2. Wenn Spieler sagt „du bist dran“: IMMER zuerst `schach-stellung` lesen (wer am Zug ist, letzter Zug, FEN, Textbrett, geschlagene Figuren, alle legalen Züge).
3. Dann `schach-zug e7e5` – Zug in UCI (z. B. e7e5, e8g8 für Rochade, a2a1q für Umwandlung) oder SAN (z. B. Nf6). Nur legale Züge, nur wenn Schwarz am Zug ist; sonst kommt eine Ablehnung mit der Liste legaler Züge.
4. `schach-neu` – neue Partie, nur wenn Spieler das will.

Ist das Brett zu, melden schach-stellung/schach-zug „Brett ist nicht offen – erst schach-brett“.
Jede Figur gleitet ca. 2 Sekunden über das Brett – Spieler sieht so jeden Zug.
