# KI-Schachbrett Version 4 · Beyhl Software – Schach gegen jede beliebige KI

Ein großes, gut lesbares Schachbrett für den Desktop, gegen das **jede KI** spielen kann, die Terminal-Befehle ausführen darf – zum Beispiel Claude Code, OpenCode mit DeepSeek oder ein lokales Modell.

Der Mensch zieht mit der Maus (Weiß), die KI zieht über einfache Befehle (Schwarz). An der KI oder am Chatprogramm muss nichts geändert werden.

## Was es kann
- Großes Brett oben in der Mitte des Fensters, gut sichtbar.
- Jeder Zug wird **sichtbar animiert** (die Figur gleitet etwa 2 Sekunden), damit man nachvollziehen kann, was passiert. Der letzte Zug bleibt farbig markiert.
- **Geschlagene Figuren** stehen links (schwarze) und rechts (weiße) neben dem Brett, mit Materialdifferenz (z. B. „+3“).
- Oben steht, gegen welche KI man spielt.
- **Neu in Version 2:** Knopf „Zug zurück“ – nimmt den eigenen letzten Zug zurück, solange die KI noch nicht gezogen hat (wie die Hand, die noch auf der Figur liegt). Danach ist er gesperrt.
- **Neu in Version 3:** Stockfish als Gegner (optional). Auswahl am Brett: „Spieler gegen KI“, „Spieler gegen Stockfish“, „KI gegen Stockfish“ oder „KI gegen KI“, dazu die Farbe (Weiß/Schwarz) und die Stockfish-Stärke von „Anfänger“ bis „Volle Stärke“. Stockfish zieht von selbst. Knopf „Neues Spiel“.
- **KI gegen KI:** Zwei verschiedene KIs (z. B. Claude in Claude Code und GPT in Codex) spielen gegeneinander – jede zieht nur ihre Farbe. Die Namen stehen in `modus.json` (`weiss_name`, `schwarz_name`).
- **Führungsanzeige:** Links oben steht groß, wer nach Material führt (z. B. „Weiß führt mit +3“) oder „Material ausgeglichen“.
- **Neu in Version 4:** Zugzähler unter den geschlagenen Figuren („Weiß: 33 Züge gemacht“) und gut sichtbare Versionsangabe im Fenster.
- Die Regeln prüft [python-chess](https://python-chess.readthedocs.io/): Die KI kann keine illegalen Züge machen. Schach, Matt, Patt, Rochade, Umwandlung – alles dabei.
- Die Partie wird gespeichert und nach versehentlichem Schließen fortgesetzt.

## Voraussetzungen
- Linux (getestet unter Linux Mint), Python 3
- `pip install python-chess PyQt5`
- Optional für Stockfish als Gegner: `sudo apt install stockfish` (Linux). **Ist Stockfish installiert, erkennt das Brett es beim Start automatisch** – die Stockfish-Auswahl erscheint dann von selbst und funktioniert sofort, ohne weitere Einstellung. Ohne Stockfish läuft alles andere wie gewohnt; die Stockfish-Auswahl wird dann einfach nicht angezeigt.

## Installation
```bash
git clone https://github.com/SualkKlaus/Schachbrett-KI.git
cd Schachbrett-KI
./install.sh
```

## Spielen
1. Der KI im Chat sagen: „Lies ANLEITUNG_FUER_KIS.md im Ordner Schachbrett-KI – ich will Schach spielen.“
2. Die KI öffnet das Brett mit `schach-brett "Ihr Name"`.
3. Du ziehst mit der Maus und sagst danach im Chat einfach „du bist dran“.
4. Die KI liest die Stellung (`schach-stellung`) und zieht (`schach-zug e7e5`).

| Befehl | Wirkung |
|---|---|
| `schach-brett "Name"` | Brett öffnen bzw. nach vorn holen |
| `schach-stellung` | Stellung als Text: wer am Zug ist, Textbrett, FEN, geschlagene Figuren, alle legalen Züge |
| `schach-zug e7e5` | Zug der KI (UCI oder SAN, z. B. `Nf6`) |
| `schach-neu` | neue Partie |

Hinweis: Sprachmodelle spielen eher schwach Schach – aber dank der Regelprüfung immer regelgerecht.

## Herkunft und Lizenz
Idee und Wunschliste: Klaus Beyhl. Programmiert mit Claude (Opus 5.5) von Anthropic.
Programm: MIT-Lizenz (siehe `LICENSE`).
Figurenbilder: aus GNOME Chess, basierend auf der Arbeit von Max Froumentin (W3C), unter der W3C Software Notice and License (siehe Hinweis in den SVG-Dateien).
