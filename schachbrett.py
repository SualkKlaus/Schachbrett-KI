#!/usr/bin/env python3
"""KI-Schachbrett Version 5 · Beyhl Software – Mensch (Weiß, Maus) gegen eine KI (Schwarz, Terminal-Befehle).

Aufruf:
  schachbrett.py gui [Name]      Fenster (wird von schach-brett gestartet)
  schachbrett.py brett [Name]    öffnen bzw. nach vorn holen
  schachbrett.py stellung        Stellung als Text
  schachbrett.py zug <Zug>       Zug der KI (UCI oder SAN)
  schachbrett.py neu             neue Partie
  schachbrett.py modus ...       Spielart/Farbe/Stärke/Namen einstellen (siehe schach-modus --hilfe)
Kanal: TCP 127.0.0.1:47321, eine JSON-Zeile hin, eine zurück.
"""
import json
import threading
import os
import socket
import subprocess
import sys
import time

import chess

ORDNER = os.path.dirname(os.path.abspath(__file__))
HINWEIS = ("WICHTIG FÜR DICH (KI): Mensch zieht mit der MAUS am Brett und sagt seinen Zug NICHT im Chat – frag ihn nie danach. "
           "Sobald er „du bist dran“ sagt: führe schach-stellung aus (dort steht sein Zug), dann schach-zug <Zug>.")
SPEICHER = os.path.join(ORDNER, "partie.json")
FIGUREN = os.path.join(ORDNER, "figuren")
PORT = 47321
VERSION_TEXT = "KI-Schachbrett Version 5 · Beyhl Software"
MODUS_DATEI = os.path.join(ORDNER, "modus.json")
import shutil
STOCKFISH = shutil.which("stockfish") or ("/usr/games/stockfish" if os.path.exists("/usr/games/stockfish") else None)
# Stufen: (Anzeige, Stockfish-Einstellungen)
STUFEN = [("Anfänger", {"Skill Level": 0}),
          ("Gelegenheitsspieler", {"Skill Level": 3}),
          ("Vereinsspieler", {"UCI_LimitStrength": True, "UCI_Elo": 1600}),
          ("Starker Spieler", {"UCI_LimitStrength": True, "UCI_Elo": 2000}),
          ("Meister", {"UCI_LimitStrength": True, "UCI_Elo": 2400}),
          ("Volle Stärke", {})]
MODI = [("ki", "Mensch gegen KI"), ("sf", "Mensch gegen Stockfish"), ("ki_sf", "KI gegen Stockfish"), ("ki_ki", "KI gegen KI")]


def lade_modus():
    try:
        with open(MODUS_DATEI) as f:
            d = json.load(f)
        return d.get("modus", "ki"), int(d.get("stufe", 1)), bool(d.get("seite", True))
    except Exception:
        return "ki", 1, True


def speichere_modus(modus, stufe, seite=True):
    try:
        d = json.load(open(MODUS_DATEI))
    except Exception:
        d = {}
    d.update({"modus": modus, "stufe": stufe, "seite": seite})
    with open(MODUS_DATEI, "w") as f:
        json.dump(d, f)


def spieler(name, modus, stufe, seite=True):
    """(Weiß-Name, Schwarz-Name, Farbe der Befehls-KI oder None).
    seite = Farbe des ERSTGENANNTEN Spielers (Mensch bzw. bei „KI gegen Stockfish“ die KI); True = Weiß."""
    sf = f"Stockfish ({STUFEN[stufe][0]})"
    if modus == "ki_ki":
        try:
            d = json.load(open(MODUS_DATEI))
            return d.get("weiss_name", "KI Weiß"), d.get("schwarz_name", "KI Schwarz"), "beide"
        except Exception:
            return "KI Weiß", "KI Schwarz", "beide"
    if modus == "sf":
        erster, zweiter, ki = "Mensch", sf, None
    elif modus == "ki_sf":
        erster, zweiter, ki = name, sf, seite
    else:
        erster, zweiter, ki = "Mensch", name, (not seite)
    return (erster, zweiter, ki) if seite else (zweiter, erster, ki)
GLEITZEIT = 2000  # ms pro Figur

WERT = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
NAMEN = {chess.PAWN: "Pawn", chess.KNIGHT: "Knight", chess.BISHOP: "Bishop",
         chess.ROOK: "Rook", chess.QUEEN: "Queen", chess.KING: "King"}


# ---------------------------------------------------------------- Speicher
def lade_partie():
    try:
        with open(SPEICHER) as f:
            d = json.load(f)
        return d.get("name") or "KI", list(d.get("moves", []))
    except Exception:
        return "KI", []


def speichere_partie(name, moves):
    tmp = SPEICHER + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"name": name, "moves": moves}, f)
    os.replace(tmp, SPEICHER)


def brett_aus_zuegen(moves):
    b = chess.Board()
    for u in moves:
        b.push_uci(u)
    return b


def ende_text(board):
    o = board.outcome(claim_draw=True)
    if o is None:
        return None
    if o.termination == chess.Termination.CHECKMATE:
        return "Schachmatt – " + ("Weiß gewinnt" if o.winner == chess.WHITE else "Schwarz gewinnt")
    gruende = {
        chess.Termination.STALEMATE: "Patt – Remis",
        chess.Termination.INSUFFICIENT_MATERIAL: "Remis – zu wenig Material",
        chess.Termination.THREEFOLD_REPETITION: "Remis – dreifache Wiederholung",
        chess.Termination.FIVEFOLD_REPETITION: "Remis – fünffache Wiederholung",
        chess.Termination.FIFTY_MOVES: "Remis – 50-Züge-Regel",
        chess.Termination.SEVENTYFIVE_MOVES: "Remis – 75-Züge-Regel",
    }
    return gruende.get(o.termination, "Remis")


def geschlagene(moves):
    """Liefert (von Weiß geschlagen, von Schwarz geschlagen) als Listen von Figurtypen."""
    b = chess.Board()
    weiss, schwarz = [], []
    for u in moves:
        m = chess.Move.from_uci(u)
        if b.is_capture(m):
            if b.is_en_passant(m):
                typ = chess.PAWN
            else:
                typ = b.piece_at(m.to_square).piece_type
            (weiss if b.turn == chess.WHITE else schwarz).append(typ)
        b.push(m)
    return weiss, schwarz


def material(board):
    w = sum(WERT[p.piece_type] for p in board.piece_map().values() if p.color == chess.WHITE)
    s = sum(WERT[p.piece_type] for p in board.piece_map().values() if p.color == chess.BLACK)
    return w - s


# ---------------------------------------------------------------- Kanal (Client)
def frage(cmd, **kw):
    kw["cmd"] = cmd
    try:
        s = socket.create_connection(("127.0.0.1", PORT), timeout=3)
    except OSError:
        return None
    with s:
        s.sendall((json.dumps(kw) + "\n").encode())
        daten = b""
        while not daten.endswith(b"\n"):
            teil = s.recv(65536)
            if not teil:
                break
            daten += teil
    try:
        return json.loads(daten.decode())
    except Exception:
        return None


NICHT_OFFEN = "Brett ist nicht offen – erst schach-brett"


def stellung_text(name, moves):
    b = brett_aus_zuegen(moves)
    z = []
    ende = ende_text(b)
    if ende:
        z.append(f"PARTIE BEENDET: {ende}. (Neue Partie nur auf des Menschen Wunsch: schach-neu)")
    else:
        ws, ss, ki = spieler(name, *lade_modus())
        farbe = "Weiß" if b.turn == chess.WHITE else "Schwarz"
        wer = ws if b.turn == chess.WHITE else ss
        if ki == "beide":
            z.append(f"AM ZUG: {farbe} = {wer}. (KI gegen KI) – NUR wenn du {wer} bist: schach-zug <Zug>. Sonst warten und später erneut schach-stellung.")
        elif ki is not None and b.turn == ki:
            z.append(f"AM ZUG: {farbe} = {name} (DU, die KI). Mach deinen Zug mit: schach-zug <Zug>")
        elif ki is None:
            z.append(f"AM ZUG: {farbe} = {wer}. Es spielt gerade Mensch gegen Stockfish – du ziehst nicht.")
        else:
            z.append(f"AM ZUG: {farbe} = {wer}. Du ({name}) musst warten, bis {wer} gezogen hat.")
    if moves:
        vor = brett_aus_zuegen(moves[:-1])
        letzt = chess.Move.from_uci(moves[-1])
        _ws, _ss, _ = spieler(name, *lade_modus())
        wer = f"{_ws} (Weiß)" if vor.turn == chess.WHITE else f"{_ss} (Schwarz)"
        z.append(f"Letzter Zug: {wer} {moves[-1]} ({vor.san(letzt)}) – Zugnummer {vor.fullmove_number}")
    else:
        z.append("Letzter Zug: – (Ausgangsstellung)")
    z.append(f"FEN: {b.fen()}")
    z.append("")
    z.append("    a b c d e f g h")
    for r in range(7, -1, -1):
        reihe = []
        for f in range(8):
            p = b.piece_at(chess.square(f, r))
            reihe.append(p.symbol() if p else ".")
        z.append(f"  {r + 1} " + " ".join(reihe) + f" {r + 1}")
    z.append("    a b c d e f g h")
    z.append("  (Großbuchstaben = Weiß/Mensch, Kleinbuchstaben = Schwarz/KI, . = leer)")
    z.append("")
    gw, gs = geschlagene(moves)
    sym = lambda t, c: chess.Piece(t, c).symbol()
    z.append("Von Weiß geschlagen:   " + (" ".join(sym(t, chess.BLACK) for t in gw) or "–"))
    z.append("Von Schwarz geschlagen: " + (" ".join(sym(t, chess.WHITE) for t in gs) or "–"))
    d = material(b)
    z.append("Material: " + ("ausgeglichen" if d == 0 else (f"Weiß +{d}" if d > 0 else f"Schwarz +{-d}")))
    z.append("")
    if not ende:
        if b.is_check():
            z.append(("SCHACH! " + ("Schwarz (du)" if b.turn == chess.BLACK else "Weiß (Mensch)") +
                      " steht im Schach."))
        legal = [m.uci() for m in b.legal_moves]
        z.append(f"Legale Züge für {'Schwarz' if b.turn == chess.BLACK else 'Weiß'} ({len(legal)}):")
        z.append(" ".join(legal))
    return "\n".join(z)


MODUS_HILFE = """schach-modus – Brett einstellen (springt sofort um, danach am besten schach-neu)

  schach-modus <spielart> [farbe] [stufe] [--weiss "Name"] [--schwarz "Name"]

  spielart:  mensch-gegen-ki | mensch-gegen-stockfish | ki-gegen-stockfish | ki-gegen-ki
  farbe:     weiss | schwarz   – Farbe des ZUERST genannten Spielers (Mensch bzw. KI)
  stufe:     anfaenger | gelegenheit | verein | stark | meister | voll   (nur mit Stockfish)
  Namen:     nur bei ki-gegen-ki:  --weiss "Claude Fable 5.2 (Medium)" --schwarz "GPT-6 Astra (Medium)"

Beispiele:
  schach-modus ki-gegen-stockfish weiss anfaenger      (du KI spielst Weiß gegen Stockfish auf Anfänger)
  schach-modus mensch-gegen-ki weiss                    (Mensch Weiß mit der Maus, du Schwarz)
  schach-modus ki-gegen-ki --weiss "Fable" --schwarz "Astra"
Ohne Angaben zeigt schach-modus die aktuelle Einstellung."""


def lage_text(name):
    """Mode-gerechte Kurzmeldung für die KI: wer spielt welche Farbe, was sie tun soll."""
    modus, stufe, seite = lade_modus()
    ws, ss, ki = spieler(name, modus, stufe, seite)
    t = f"Weiß: {ws} – Schwarz: {ss}."
    if ki is None:
        return t + " Mensch spielt gegen Stockfish – du (KI) ziehst in dieser Partie NICHT."
    if ki == "beide":
        return t + (" KI gegen KI: Jede KI zieht nur ihre eigene Farbe. Mit schach-stellung nachsehen, wer am Zug ist; "
                    "bist du dran: schach-zug <Zug>, sonst warten und erneut schach-stellung.")
    farbe = "Weiß" if ki else "Schwarz"
    t += f" DU (die KI, {name}) spielst {farbe}."
    if modus == "ki_sf":
        t += (" Gegner ist Stockfish, er zieht von selbst. Du brauchst auf niemanden zu warten: "
              "führe schach-stellung aus; steht dort, dass du am Zug bist, sofort schach-zug <Zug>. "
              "Danach kurz warten, wieder schach-stellung, bis die Partie beendet ist.")
    else:
        t += (" Mensch zieht mit der MAUS und sagt seinen Zug NICHT im Chat – frag ihn nie danach. "
              "Bei „du bist dran“: schach-stellung ausführen, dann schach-zug <Zug>.")
        if ki:
            t += " Da du Weiß hast, beginnst DU – führe jetzt gleich schach-stellung und schach-zug aus."
    return t


def cli(argv):
    befehl = argv[0] if argv else ""
    if befehl == "brett":
        name = " ".join(argv[1:]).strip()
        r = frage("vorne", name=name)
        if r is not None:
            print("Brett ist schon offen und wurde nach vorn geholt."); print(lage_text(r['name']))
            return 0
        args = [sys.executable, os.path.abspath(__file__), "gui"] + ([name] if name else [])
        subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=open(os.path.join(ORDNER, "fenster.log"), "a"),
                         start_new_session=True, cwd=ORDNER)
        for _ in range(60):
            time.sleep(0.25)
            r = frage("info")
            if r is not None:
                b = brett_aus_zuegen(r["moves"])
                fort = " (letzte Partie geladen)" if r["moves"] else ""
                print(f"Brett ist offen{fort}. "
                      ""); print(lage_text(r['name']))
                return 0
        print("Fehler: Brett-Fenster startet nicht (siehe fenster.log im Ordner Schachbrett KI).")
        return 1

    if befehl == "stellung":
        r = frage("info")
        if r is None:
            print(NICHT_OFFEN)
            return 1
        print(stellung_text(r["name"], r["moves"]))
        return 0

    if befehl == "zug":
        if len(argv) < 2:
            print("Aufruf: schach-zug <Zug>   (z. B. schach-zug e7e5 oder schach-zug Nf6)")
            return 1
        r = frage("zug", zug=" ".join(argv[1:]))
        if r is None:
            print(NICHT_OFFEN)
            return 1
        print(r["text"])
        return 0 if r.get("ok") else 1

    if befehl == "modus":
        args = argv[1:]
        if args and args[0] in ("--hilfe", "-h", "hilfe", "--help"):
            print(MODUS_HILFE); return 0
        modus, stufe, seite = lade_modus()
        try:
            d = json.load(open(MODUS_DATEI))
        except Exception:
            d = {}
        if not args:
            ws, ss, _ = spieler(lade_partie()[0], modus, stufe, seite)
            print(f"Aktuell: Spielart {modus}, Weiß: {ws}, Schwarz: {ss}, Stockfish-Stufe: {STUFEN[stufe][0]}")
            print(MODUS_HILFE); return 0
        art = {"mensch-gegen-ki": "ki", "mensch-gegen-stockfish": "sf", "klaus-gegen-ki": "ki", "klaus-gegen-stockfish": "sf", "ki-gegen-stockfish": "ki_sf", "ki-gegen-ki": "ki_ki"}
        stu = {"anfaenger": 0, "anfänger": 0, "gelegenheit": 1, "verein": 2, "stark": 3, "meister": 4, "voll": 5}
        rest = []; i = 0
        while i < len(args):
            a = args[i].lower()
            if a in ("--weiss", "--weiß") and i + 1 < len(args):
                d["weiss_name"] = args[i + 1]; i += 2; continue
            if a == "--schwarz" and i + 1 < len(args):
                d["schwarz_name"] = args[i + 1]; i += 2; continue
            rest.append(a); i += 1
        for a in rest:
            if a in art: modus = art[a]
            elif a in ("weiss", "weiß"): seite = True
            elif a == "schwarz": seite = False
            elif a in stu: stufe = stu[a]
            else:
                print(f"Unbekannt: „{a}“."); print(MODUS_HILFE); return 1
        if modus in ("sf", "ki_sf") and not STOCKFISH:
            print("Stockfish ist nicht installiert – diese Spielart geht nicht."); return 1
        d.update({"modus": modus, "stufe": stufe, "seite": seite})
        json.dump(d, open(MODUS_DATEI, "w"))
        frage("modus")          # offenes Brett liest neu ein
        name = lade_partie()[0]
        ws, ss, _ = spieler(name, modus, stufe, seite)
        print(f"Eingestellt: Weiß: {ws} – Schwarz: {ss}" + (f" – Stockfish-Stufe: {STUFEN[stufe][0]}" if modus in ("sf", "ki_sf") else ""))
        print("Für eine neue Partie jetzt: schach-neu")
        return 0

    if befehl == "neu":
        r = frage("neu")
        if r is None:
            name, _ = lade_partie()
            speichere_partie(name, [])
            print("Neue Partie vorbereitet (Brett ist zu). Öffnen mit: schach-brett")
            return 0
        print("Neue Partie gestartet."); print(lage_text(r['name']))
        return 0

    print(__doc__)
    return 1


# ---------------------------------------------------------------- Fenster
def gui(argv):
    from PyQt5.QtCore import Qt, QTimer, QElapsedTimer, QRectF, QPointF, QByteArray
    from PyQt5.QtGui import (QPainter, QColor, QFont, QPixmap, QPen, QBrush, QIcon,
                             QGuiApplication, QRadialGradient)
    from PyQt5.QtNetwork import QTcpServer, QHostAddress
    from PyQt5.QtSvg import QSvgRenderer
    from PyQt5.QtWidgets import (QApplication, QWidget, QDialog, QHBoxLayout, QVBoxLayout,
                                 QPushButton, QLabel, QComboBox)
    from PyQt5.QtCore import QSize

    app = QApplication(sys.argv)

    renderer = {}
    for c, cn in ((chess.WHITE, "white"), (chess.BLACK, "black")):
        for t, tn in NAMEN.items():
            renderer[(c, t)] = QSvgRenderer(os.path.join(FIGUREN, f"{cn}{tn}.svg"))
    cache = {}

    def figur_pixmap(color, typ, groesse):
        groesse = max(8, int(groesse))
        k = (color, typ, groesse)
        if k not in cache:
            pm = QPixmap(groesse, groesse)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            renderer[(color, typ)].render(p, QRectF(0, 0, groesse, groesse))
            p.end()
            cache[k] = pm
        return cache[k]

    class Umwandlung(QDialog):
        def __init__(self, parent):
            super().__init__(parent)
            self.setWindowTitle("Bauernumwandlung")
            self.wahl = chess.QUEEN
            lay = QVBoxLayout(self)
            lab = QLabel("Bauer wird zu:")
            lab.setFont(QFont("Sans", 26, QFont.Bold))
            lay.addWidget(lab)
            reihe = QHBoxLayout()
            for typ, txt in ((chess.QUEEN, "Dame"), (chess.ROOK, "Turm"),
                             (chess.BISHOP, "Läufer"), (chess.KNIGHT, "Springer")):
                b = QPushButton(txt)
                b.setIcon(QIcon(figur_pixmap(parent.mensch_farbe() if parent.mensch_farbe() is not None else chess.WHITE, typ, 120)))
                b.setIconSize(QSize(120, 120))
                b.setFont(QFont("Sans", 22, QFont.Bold))
                b.setMinimumSize(200, 200)
                b.clicked.connect(lambda _=False, t=typ: self.waehle(t))
                reihe.addWidget(b)
                if typ == chess.QUEEN:
                    b.setDefault(True)
                    b.setFocus()
            lay.addLayout(reihe)

        def waehle(self, t):
            self.wahl = t
            self.accept()

    class Brett(QWidget):
        def __init__(self, name):
            super().__init__()
            gespeichert_name, moves = lade_partie()
            self.name = name or gespeichert_name
            try:
                self.board = brett_aus_zuegen(moves)
            except Exception:
                self.board = chess.Board()
            self.vis = self.board.copy()          # sichtbare Stellung (hinkt bei Animation hinterher)
            self.queue = []                       # Liste von Zügen, jeder = Liste von Schritten
            self.schritt = None                   # aktueller Schritt
            self.uhr = QElapsedTimer()
            self.timer = QTimer(self)
            self.timer.setInterval(15)
            self.timer.timeout.connect(self.tick)
            self.auswahl = None
            self.drag_von = None
            self.drag_pos = None
            self.press_pos = None
            self.setMouseTracking(True)
            self.setMinimumSize(900, 700)
            # Knopf „Zug zurück“: nur eigener letzter Zug, solange die KI noch nicht gezogen hat
            self.btn_zurueck = QPushButton("↶ Zurück", self)
            self.btn_zurueck.setStyleSheet("QPushButton{font:bold 22px Sans;color:white;background:#2e6bd6;border-radius:12px;padding:10px}"
                                           "QPushButton:disabled{background:#7a7a7a;color:#cfcfcf}")
            self.btn_zurueck.clicked.connect(self.zug_zurueck)
            self.btn_neu = QPushButton("Neues Spiel", self)
            self.btn_neu.setStyleSheet("QPushButton{font:bold 22px Sans;color:white;background:#15803d;border-radius:12px;padding:10px}")
            self.btn_neu.clicked.connect(self.neues_spiel_knopf)
            # Spielart + Stockfish-Stärke
            self.modus, self.stufe, self.seite = lade_modus()
            stil = ("QComboBox{font:bold 20px Sans;padding:6px;background:#f59e0b;color:#000;border-radius:8px}"
                    "QComboBox QAbstractItemView{font:bold 20px Sans;background:#ffffff;color:#000000;outline:0}"
                    "QComboBox QAbstractItemView::item{min-height:40px;padding:4px 8px;color:#000000;background:#ffffff}"
                    "QComboBox QAbstractItemView::item:selected{background:#f59e0b;color:#000000}"
                    "QComboBox QAbstractItemView::item:hover{background:#f59e0b;color:#000000}")
            self.cb_modus = QComboBox(self); self.cb_modus.setStyleSheet(stil)
            for k, t in MODI:
                if k != "ki" and not STOCKFISH:
                    continue          # Stockfish nicht installiert -> nur „gegen KI“
                self.cb_modus.addItem(t, k)
            if not STOCKFISH:
                self.modus = "ki"
            idx = self.cb_modus.findData(self.modus)
            self.cb_modus.setCurrentIndex(idx if idx >= 0 else 0)
            self.cb_stufe = QComboBox(self); self.cb_stufe.setStyleSheet(stil)
            for t, _ in STUFEN: self.cb_stufe.addItem("Stockfish: " + t)
            self.cb_stufe.setCurrentIndex(max(0, min(len(STUFEN) - 1, self.stufe)))
            self.cb_seite = QComboBox(self); self.cb_seite.setStyleSheet(stil)
            self.cb_seite.addItems(["Weiß", "Schwarz"])
            self.cb_seite.setCurrentIndex(0 if self.seite else 1)
            self.cb_seite.currentIndexChanged.connect(self.modus_geaendert)
            from PyQt5.QtWidgets import QListView
            for cb in (self.cb_modus, self.cb_seite, self.cb_stufe):
                cb.setView(QListView())
            self.cb_modus.currentIndexChanged.connect(self.modus_geaendert)
            self.cb_stufe.currentIndexChanged.connect(self.modus_geaendert)
            self.engine = None
            self.sf_laeuft = False
            self.sf_zug = None
            self.sf_uhr = QTimer(self); self.sf_uhr.setInterval(300); self.sf_uhr.timeout.connect(self.sf_pruefen); self.sf_uhr.start()
            self.seite_text()
            self.titel_setzen()
            speichere_partie(self.name, self.zuege())

        # ---- Hilfen
        def zuege(self):
            return [m.uci() for m in self.board.move_stack]

        def titel_setzen(self):
            ws, ss, _ = spieler(self.name, getattr(self, "modus", "ki"), getattr(self, "stufe", 1), getattr(self, "seite", True))
            self.setWindowTitle(f"KI-Schachbrett Version 5 · Beyhl Software – {ws} gegen {ss}")

        def animiert(self):
            return self.schritt is not None or bool(self.queue)

        def modus_geaendert(self, *_):
            self.modus = self.cb_modus.currentData()
            self.stufe = self.cb_stufe.currentIndex()
            self.seite = self.cb_seite.currentIndex() == 0
            speichere_modus(self.modus, self.stufe, self.seite)
            self.seite_text()
            self.titel_setzen()
            self.update()

        def sp(self):
            return spieler(self.name, self.modus, self.stufe, self.seite)

        def mensch_farbe(self):
            return self.seite if self.modus in ("ki", "sf") else None

        def sf_farbe(self):
            return (not self.seite) if self.modus in ("sf", "ki_sf") else None

        def seite_text(self):
            self.cb_seite.setVisible(self.modus != "ki_ki")
            if self.modus == "ki":
                t = ("Mensch Weiß – KI Schwarz", "Mensch Schwarz – KI Weiß")
            elif self.modus == "sf":
                t = ("Mensch Weiß – Stockfish Schwarz", "Mensch Schwarz – Stockfish Weiß")
            else:
                t = ("KI Weiß – Stockfish Schwarz", "KI Schwarz – Stockfish Weiß")
            for i in range(2):
                self.cb_seite.setItemText(i, t[i])

        def sf_pruefen(self):
            self.cb_stufe.setVisible(self.modus in ("sf", "ki_sf"))
            if self.sf_zug is not None and not self.animiert():
                zug, self.sf_zug = self.sf_zug, None
                if self.modus in ("sf", "ki_sf") and zug in self.board.legal_moves:
                    self.zug_anhaengen(zug)
                return
            if (STOCKFISH and self.modus in ("sf", "ki_sf") and not self.sf_laeuft and not self.animiert()
                    and self.board.turn == self.sf_farbe() and not self.board.is_game_over(claim_draw=True)):
                self.sf_laeuft = True
                brett, stufe = self.board.copy(), self.stufe
                def denken():
                    try:
                        import chess.engine
                        if self.engine is None:
                            self.engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
                        opt = {"Skill Level": 20, "UCI_LimitStrength": False}
                        opt.update(STUFEN[stufe][1])
                        self.engine.configure(opt)
                        r = self.engine.play(brett, chess.engine.Limit(time=1.0))
                        self.sf_zug = r.move
                    except Exception as e:
                        open(os.path.join(ORDNER, "fenster.log"), "a").write(f"Stockfish-Fehler: {e}\n")
                    finally:
                        self.sf_laeuft = False
                threading.Thread(target=denken, daemon=True).start()
                self.update()

        def mensch_darf(self):
            return (self.modus in ("ki", "sf") and not self.animiert() and self.board.turn == self.mensch_farbe()
                    and not self.board.is_game_over(claim_draw=True))

        # ---- Geometrie
        def geo(self):
            W, H = self.width(), self.height()
            self.cm = 52                          # Platz für Koordinaten
            # Brett ganz oben, waagrecht mittig, groß wie in GNOME Chess (Felder ca. 100 px, Laptop verdeckt sonst unten)
            self.sq = max(30, min(100, (H - 6 - self.cm - 10) // 8, int(W * 0.5) // 8))
            self.bx = (W - 8 * self.sq) // 2
            self.by = 6
            self.px = self.bx + 8 * self.sq + 40  # rechte Spalte: Titel, Status, geschlagene Weiße
            self.pw = W - self.px - 20
            self.lx = 20                           # linke Spalte: geschlagene Schwarze
            self.lw = self.bx - self.cm - 30 - self.lx

        def feld_rect(self, sq):
            f, r = chess.square_file(sq), chess.square_rank(sq)
            return QRectF(self.bx + f * self.sq, self.by + (7 - r) * self.sq, self.sq, self.sq)

        def feld_an(self, pos):
            f = int((pos.x() - self.bx) // self.sq)
            r = 7 - int((pos.y() - self.by) // self.sq)
            if 0 <= f < 8 and 0 <= r < 8 and pos.x() >= self.bx and pos.y() >= self.by:
                return chess.square(f, r)
            return None

        # ---- Animation
        def zug_anhaengen(self, move):
            pre = self.board.copy()
            self.board.push(move)
            speichere_partie(self.name, self.zuege())
            karte = dict(pre.piece_map())
            fig = karte[move.from_square]
            schritte = []
            if pre.is_castling(move):
                kingside = chess.square_file(move.to_square) > chess.square_file(move.from_square)
                rang = chess.square_rank(move.from_square)
                k_ziel = chess.square(6 if kingside else 2, rang)
                t_von = chess.square(7 if kingside else 0, rang)
                t_ziel = chess.square(5 if kingside else 3, rang)
                b1 = dict(karte)
                del b1[move.from_square]
                schritte.append((b1, fig, move.from_square, k_ziel, move))
                b2 = dict(b1)
                turm = b2.pop(t_von)
                b2[k_ziel] = fig
                schritte.append((b2, turm, t_von, t_ziel, move))
            else:
                b1 = dict(karte)
                del b1[move.from_square]
                schritte.append((b1, fig, move.from_square, move.to_square, move))
            self.queue.append(schritte)
            if self.schritt is None:
                self.naechster_schritt()
            self.update()

        def naechster_schritt(self):
            if not self.queue:
                self.schritt = None
                self.timer.stop()
                self.update()
                return
            schritte = self.queue[0]
            self.schritt = schritte.pop(0)
            if not schritte:
                self.queue.pop(0)
                self.schritt = self.schritt + (True,)   # letzter Schritt dieses Zuges
            else:
                self.schritt = self.schritt + (False,)
            self.uhr.start()
            self.timer.start()

        def tick(self):
            if self.schritt and self.uhr.elapsed() >= GLEITZEIT:
                if self.schritt[5]:
                    if self.schritt[4] is None:
                        self.vis = self.board.copy()
                    else:
                        self.vis.push(self.schritt[4])
                self.schritt = None
                self.naechster_schritt()
            self.update()

        def neues_spiel_knopf(self):
            from PyQt5.QtWidgets import QMessageBox
            if self.board.move_stack and not self.board.is_game_over(claim_draw=True):
                f = QMessageBox(self); f.setWindowTitle("Neues Spiel"); f.setText("Laufende Partie beenden und neu anfangen?")
                f.setStyleSheet("QLabel{font:bold 22px Sans} QPushButton{font:bold 20px Sans;min-width:120px;min-height:44px}")
                ja = f.addButton("Ja, neu", QMessageBox.YesRole); f.addButton("Nein", QMessageBox.NoRole); f.exec_()
                if f.clickedButton() is not ja:
                    return
            self.sf_zug = None
            self.neu()

        def zurueck_moeglich(self):
            return (self.modus in ("ki", "sf") and not self.sf_laeuft and self.sf_zug is None
                    and not self.animiert() and self.board.move_stack and self.board.turn != self.mensch_farbe()
                    and not self.board.is_game_over(claim_draw=True))

        def zug_zurueck(self):
            if not self.zurueck_moeglich():
                return
            move = self.board.pop()                       # des Menschen letzter Zug
            speichere_partie(self.name, self.zuege())
            karte = dict(self.vis.piece_map())
            fig = karte.pop(move.to_square, None)
            if fig is None:
                self.vis = self.board.copy(); self.update(); return
            weg = self.board.piece_at(move.to_square)     # geschlagene Figur kommt zurück
            if weg:
                karte[move.to_square] = weg
            if move.promotion:
                fig = chess.Piece(chess.PAWN, self.mensch_farbe())
            # sichtbar zurückgleiten; am Ende Stellung exakt übernehmen (move=None)
            self.queue.append([(karte, fig, move.to_square, move.from_square, None)])
            if self.schritt is None:
                self.naechster_schritt()
            self.update()

        def neu(self):
            self.queue.clear()
            self.schritt = None
            self.timer.stop()
            self.board = chess.Board()
            self.vis = chess.Board()
            self.auswahl = self.drag_von = None
            speichere_partie(self.name, [])
            self.update()

        # ---- Befehle
        def befehl(self, d):
            cmd = d.get("cmd")
            if cmd == "info":
                return {"name": self.name, "moves": self.zuege()}
            if cmd == "vorne":
                if d.get("name"):
                    self.name = d["name"]
                    self.titel_setzen()
                    speichere_partie(self.name, self.zuege())
                    self.update()
                self.nach_vorn()
                return {"name": self.name, "moves": self.zuege()}
            if cmd == "modus":
                self.modus, self.stufe, self.seite = lade_modus()
                for cb in (self.cb_modus, self.cb_stufe, self.cb_seite): cb.blockSignals(True)
                i = self.cb_modus.findData(self.modus); self.cb_modus.setCurrentIndex(i if i >= 0 else 0)
                self.cb_stufe.setCurrentIndex(self.stufe); self.cb_seite.setCurrentIndex(0 if self.seite else 1)
                for cb in (self.cb_modus, self.cb_stufe, self.cb_seite): cb.blockSignals(False)
                self.seite_text(); self.titel_setzen(); self.update()
                return {"ok": True}
            if cmd == "neu":
                self.neu()
                return {"name": self.name, "moves": []}
            if cmd == "zug":
                return self.ki_zug(str(d.get("zug", "")).strip())
            return {"ok": False, "text": "Unbekannter Befehl"}

        def ki_zug(self, text):
            b = self.board
            legal = " ".join(m.uci() for m in b.legal_moves)
            ende = ende_text(b)
            if ende:
                return {"ok": False, "text": f"Abgelehnt: Die Partie ist beendet ({ende})."}
            if self.modus == "sf":
                return {"ok": False, "text": "Abgelehnt: Gerade spielt Mensch gegen Stockfish – du ziehst nicht."}
            ki = self.sp()[2]
            if ki == "beide":
                ki = b.turn
            if b.turn != ki:
                return {"ok": False, "text": "Abgelehnt: Du bist nicht am Zug. "
                        "Warte auf „du bist dran“ und lies dann zuerst schach-stellung."}
            move = None
            roh = text.replace("-", "").replace(" ", "")
            try:
                m = chess.Move.from_uci(roh.lower())
                if m in b.legal_moves:
                    move = m
            except ValueError:
                pass
            if move is None:
                try:
                    move = b.parse_san(text)
                except ValueError:
                    move = None
            if move is None:
                return {"ok": False, "text": f"Abgelehnt: „{text}“ ist kein legaler Zug für {'Weiß' if ki else 'Schwarz'} in "
                        f"dieser Stellung.\nLegale Züge ({b.legal_moves.count()}): {legal}"}
            san = b.san(move)
            self.zug_anhaengen(move)
            t = f"Zug ausgeführt: {move.uci()} ({san}). Die Figur gleitet jetzt sichtbar über das Brett."
            ende = ende_text(self.board)
            if ende:
                t += f"\nPARTIE BEENDET: {ende}."
            else:
                if self.modus == "ki_ki":
                    t += "\nJetzt ist die andere KI am Zug. Warte und lies später wieder schach-stellung."
                elif self.modus == "ki_sf":
                    t += "\nJetzt denkt Stockfish und zieht von selbst. Lies danach wieder schach-stellung."
                else:
                    if self.board.is_check():
                        t += "\nMensch steht im Schach."
                    t += "\nJetzt ist Mensch am Zug – warte auf sein „du bist dran“."
            return {"ok": True, "text": t}

        def nach_vorn(self):
            self.showMaximized()
            self.raise_()
            self.activateWindow()
            try:
                subprocess.Popen(["xdotool", "windowactivate", str(int(self.winId()))],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        # ---- Maus
        def mousePressEvent(self, e):
            if e.button() != Qt.LeftButton or not self.mensch_darf():
                return
            sq = self.feld_an(e.pos())
            if sq is None:
                self.auswahl = None
                self.update()
                return
            p = self.board.piece_at(sq)
            if self.auswahl is not None and sq != self.auswahl and not (p and p.color == self.mensch_farbe()):
                self.versuche_zug(self.auswahl, sq)
                return
            if p and p.color == self.mensch_farbe():
                self.auswahl = sq
                self.drag_von = sq
                self.drag_pos = e.pos()
                self.press_pos = e.pos()
            else:
                self.auswahl = None
            self.update()

        def mouseMoveEvent(self, e):
            if self.drag_von is not None:
                self.drag_pos = e.pos()
                self.update()

        def mouseReleaseEvent(self, e):
            if e.button() != Qt.LeftButton or self.drag_von is None:
                return
            von = self.drag_von
            self.drag_von = None
            ziel = self.feld_an(e.pos())
            if ziel is not None and ziel != von:
                self.versuche_zug(von, ziel)
            self.update()

        def versuche_zug(self, von, ziel):
            kandidaten = [m for m in self.board.legal_moves
                          if m.from_square == von and m.to_square == ziel]
            if not kandidaten:
                self.auswahl = None
                self.update()
                return
            move = kandidaten[0]
            if len(kandidaten) > 1 or move.promotion:
                self.drag_von = None
                self.repaint()
                dlg = Umwandlung(self)
                dlg.exec_()
                move = chess.Move(von, ziel, promotion=dlg.wahl)
            self.auswahl = None
            self.drag_von = None
            self.zug_anhaengen(move)

        # ---- Zeichnen
        def paintEvent(self, ev):
            self.geo()
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            W = self.width()
            p.fillRect(self.rect(), QColor("#8a8a8a"))   # mittelgrau
            sq = self.sq

            # Titel + Status klein rechts oben neben dem Brett
            p.setPen(QColor("#101010"))
            p.setFont(QFont("Sans", 19, QFont.Bold))
            titel_r = QRectF(self.px, self.by, self.pw, 90)
            p.drawText(titel_r, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                       "Weiß: {}\nSchwarz: {}".format(*self.sp()[:2]))
            ende = None if self.animiert() else ende_text(self.vis)
            if ende:
                st, farbe = ende, "#5a0000"
            elif self.animiert():
                st, farbe = "Zug wird gezeigt …", "#0b2f80"
            elif self.sf_laeuft:
                st, farbe = "Stockfish denkt …", "#0b2f80"
            elif self.vis.turn == chess.WHITE:
                st = self.sp()[0] + " (Weiß) ist am Zug" + ("  –  SCHACH!" if self.vis.is_check() else "")
                farbe = "#101010" if not self.vis.is_check() else "#900000"
            else:
                st = self.sp()[1] + " (Schwarz) ist am Zug" + ("  –  SCHACH!" if self.vis.is_check() else "")
                farbe = "#101010" if not self.vis.is_check() else "#900000"
            p.setPen(QColor(farbe))
            p.setFont(QFont("Sans", 19, QFont.Bold))
            p.drawText(QRectF(self.px, self.by + 95, self.pw, 90),
                       Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, st)
            oben_frei = self.by + 195   # darunter beginnen die Geschlagenen

            # Felder
            hell, dunkel = QColor("#f0d9b5"), QColor("#b58863")
            for s in chess.SQUARES:
                f, r = chess.square_file(s), chess.square_rank(s)
                p.fillRect(self.feld_rect(s), hell if (f + r) % 2 else dunkel)

            # letzter Zug / laufender Zug markieren
            mark = None
            if self.schritt:
                mark = self.schritt[4]
            elif self.vis.move_stack:
                mark = self.vis.peek()
            if mark:
                for s in (mark.from_square, mark.to_square):
                    p.fillRect(self.feld_rect(s), QColor(255, 210, 0, 150))
                    pen = QPen(QColor("#e08a00"), max(3, sq // 25))
                    p.setPen(pen)
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(self.feld_rect(s).adjusted(2, 2, -2, -2))

            # Auswahl + Zielpunkte
            if self.auswahl is not None and self.mensch_darf():
                p.fillRect(self.feld_rect(self.auswahl), QColor(60, 140, 255, 140))
                for m in self.board.legal_moves:
                    if m.from_square == self.auswahl:
                        r = self.feld_rect(m.to_square)
                        p.setPen(Qt.NoPen)
                        p.setBrush(QColor(30, 90, 200, 170))
                        if self.board.piece_at(m.to_square):
                            p.setBrush(Qt.NoBrush)
                            p.setPen(QPen(QColor(30, 90, 200, 200), sq // 12))
                            p.drawEllipse(r.center(), sq * 0.42, sq * 0.42)
                        else:
                            p.drawEllipse(r.center(), sq * 0.16, sq * 0.16)

            # Figuren
            if self.schritt:
                karte = self.schritt[0]
            else:
                karte = self.vis.piece_map()
            # König im Schach rot
            if not self.schritt and self.vis.is_check():
                k = self.vis.king(self.vis.turn)
                if k is not None:
                    r = self.feld_rect(k)
                    g = QRadialGradient(r.center(), sq * 0.6)
                    g.setColorAt(0, QColor(255, 0, 0, 220))
                    g.setColorAt(1, QColor(255, 0, 0, 0))
                    p.fillRect(r, QBrush(g))
            for s, fig in karte.items():
                if s == self.drag_von and self.drag_pos is not None:
                    continue
                r = self.feld_rect(s)
                p.drawPixmap(r.toRect(), figur_pixmap(fig.color, fig.piece_type, sq))

            # Koordinaten
            p.setPen(QColor("#101010"))
            p.setFont(QFont("Sans", max(14, int(sq * 0.30)), QFont.Bold))
            for i in range(8):
                p.drawText(QRectF(self.bx + i * sq, self.by + 8 * sq, sq, self.cm),
                           Qt.AlignCenter, "abcdefgh"[i])
                p.drawText(QRectF(self.bx - self.cm - 6, self.by + (7 - i) * sq, self.cm, sq),
                           Qt.AlignCenter, str(i + 1))

            # gleitende Figur
            if self.schritt:
                _, fig, von, nach, _, _ = self.schritt
                t = min(1.0, self.uhr.elapsed() / GLEITZEIT)
                t = t * t * (3 - 2 * t)
                a, b = self.feld_rect(von), self.feld_rect(nach)
                x = a.x() + (b.x() - a.x()) * t
                y = a.y() + (b.y() - a.y()) * t
                gr = sq * 1.1
                off = (gr - sq) / 2
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 70))
                p.drawEllipse(QPointF(x + sq / 2 + 6, y + sq / 2 + 8), sq * 0.42, sq * 0.42)
                p.drawPixmap(int(x - off), int(y - off), figur_pixmap(fig.color, fig.piece_type, gr))

            # gezogene Figur (Maus)
            if self.drag_von is not None and self.drag_pos is not None:
                fig = self.board.piece_at(self.drag_von)
                if fig:
                    gr = sq * 1.1
                    p.drawPixmap(int(self.drag_pos.x() - gr / 2), int(self.drag_pos.y() - gr / 2),
                                 figur_pixmap(fig.color, fig.piece_type, gr))

            # Geschlagene: LINKS die schwarzen, RECHTS die weißen
            gw, gs = geschlagene([m.uci() for m in self.vis.move_stack])
            d = material(self.vis)

            def block(titel, figs, farbe, x, breite, y, plus):
                cap = int(min(sq * 0.9, breite / 5.2))
                proReihe = max(1, int(breite // cap))
                figs = sorted(figs, key=lambda t: -WERT[t] if t != chess.PAWN else 0)
                reihen = max(2, (len(figs) + proReihe - 1) // proReihe)
                p.setPen(QColor("#101010"))
                p.setFont(QFont("Sans", 20, QFont.Bold))
                p.drawText(QRectF(x, y, breite, 40), Qt.AlignLeft | Qt.AlignVCenter, titel)
                if False:
                    fm = p.fontMetrics()
                    p.setPen(QColor("#004d00"))
                    p.setFont(QFont("Sans", 30, QFont.Bold))
                    p.drawText(QRectF(x + fm.width(titel) + 20, y - 4, 150, 48),
                               Qt.AlignLeft | Qt.AlignVCenter, f"+{plus}")
                p.setBrush(QColor("#9c9c9c"))
                p.setPen(QPen(QColor("#6e6e6e"), 2))
                p.drawRoundedRect(QRectF(x - 8, y + 44, breite + 8, reihen * cap + 8), 12, 12)
                self._block_unten = y + 44 + reihen * cap + 8
                for i, t in enumerate(figs):
                    xx = x + (i % proReihe) * cap
                    yy = y + 48 + (i // proReihe) * cap
                    p.drawPixmap(int(xx), int(yy), figur_pixmap(farbe, t, cap))

            # Deutliche Führungsanzeige links oben (statt nur „+3“)
            ws_, ss_ = self.sp()[0], self.sp()[1]
            if d > 0:
                fuehr, fc = f"Weiß führt mit +{d}\n({ws_})", "#004d00"
            elif d < 0:
                fuehr, fc = f"Schwarz führt mit +{-d}\n({ss_})", "#004d00"
            else:
                fuehr, fc = "Material\nausgeglichen", "#101010"
            p.setPen(QColor(fc))
            p.setFont(QFont("Sans", 24, QFont.Bold))
            p.drawText(QRectF(self.lx, self.by + 20, self.lw, oben_frei - self.by - 30),
                       Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, fuehr)
            block("Geschlagene Schwarze", gw, chess.BLACK, self.lx, self.lw, oben_frei,
                  d if d > 0 else 0)
            block("Geschlagene Weiße", gs, chess.WHITE, self.px, self.pw, oben_frei,
                  -d if d < 0 else 0)

            # Knopf „Zug zurück“ rechts unter den geschlagenen Weißen
            self.btn_zurueck.setGeometry(int(self.px), int(self.by + 5.2 * sq), int(min(self.pw, 330) // 2 - 5), 70)
            self.btn_neu.setGeometry(int(self.px + min(self.pw, 330) // 2 + 5), int(self.by + 5.2 * sq), int(min(self.pw, 330) // 2 - 5), 70)
            self.btn_neu.show()
            self.btn_zurueck.setEnabled(bool(self.zurueck_moeglich()))
            self.btn_zurueck.show()
            self.cb_modus.setGeometry(int(self.px), int(self.by + 5.2 * sq + 85), int(min(self.pw, 330)), 50)
            self.cb_seite.setGeometry(int(self.px), int(self.by + 5.2 * sq + 145), int(min(self.pw, 330)), 50)
            self.cb_stufe.setGeometry(int(self.px), int(self.by + 5.2 * sq + 205), int(min(self.pw, 330)), 50)
            self.cb_seite.setVisible(self.modus != "ki_ki")
            self.cb_modus.show()

            # Zugzähler unter den Geschlagenen (mit Abstand)
            zw = (len(self.vis.move_stack) + 1) // 2      # Weiß zieht zuerst
            zs = len(self.vis.move_stack) // 2
            unten = getattr(self, "_block_unten", oben_frei + 200) + 10
            p.setPen(QColor("#101010"))
            p.setFont(QFont("Sans", 20, QFont.Bold))
            p.drawText(QRectF(self.lx, unten, self.lw, 36), Qt.AlignLeft | Qt.AlignVCenter,
                       f"Schwarz: {zs} Züge gemacht")
            p.drawText(QRectF(self.px, unten, self.pw, 36), Qt.AlignLeft | Qt.AlignVCenter,
                       f"Weiß: {zw} Züge gemacht")
            # Versionsangabe gut sichtbar unten links
            p.setPen(QColor("#202020"))
            p.setFont(QFont("Sans", 18, QFont.Bold))
            p.drawText(QRectF(self.lx, self.height() - 60, self.lw + 400, 40), Qt.AlignLeft | Qt.AlignVCenter, VERSION_TEXT)

            # Spielende groß
            if ende:
                band = QRectF(self.bx, self.by + 2.8 * sq, 8 * sq, 2.4 * sq)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 190))
                p.drawRoundedRect(band, 20, 20)
                p.setPen(QColor("#ffd75e"))
                f = QFont("Sans", max(20, int(sq * 0.38)), QFont.Bold)
                p.setFont(f)
                teile = ende.split(" – ")
                p.drawText(band, Qt.AlignCenter | Qt.TextWordWrap, "\n".join(teile))
            p.end()

    # ---- Start
    name = " ".join(argv).strip()
    server = QTcpServer()
    if not server.listen(QHostAddress.LocalHost, PORT):
        frage("vorne", name=name)
        return 0
    w = Brett(name)

    puffer = {}

    def neue_verbindung():
        while server.hasPendingConnections():
            s = server.nextPendingConnection()
            puffer[s] = b""

            def lesen(s=s):
                puffer[s] += bytes(s.readAll())
                if b"\n" in puffer[s]:
                    zeile = puffer[s].split(b"\n", 1)[0]
                    try:
                        antwort = w.befehl(json.loads(zeile.decode()))
                    except Exception as ex:
                        antwort = {"ok": False, "text": f"Fehler im Brett: {ex}"}
                    s.write(QByteArray((json.dumps(antwort) + "\n").encode()))
                    s.flush()
                    s.disconnectFromHost()
                    puffer.pop(s, None)

            s.readyRead.connect(lesen)
            s.disconnected.connect(s.deleteLater)

    server.newConnection.connect(neue_verbindung)

    # großer Monitor (x >= 1920) bevorzugt
    ziel = None
    for sc in QGuiApplication.screens():
        if sc.geometry().x() >= 1920:
            ziel = sc
    if ziel is None:
        ziel = QGuiApplication.primaryScreen()
    g = ziel.availableGeometry()
    w.setGeometry(g.x() + 50, g.y() + 50, g.width() - 100, g.height() - 100)
    w.showMaximized()
    QTimer.singleShot(300, w.nach_vorn)
    return app.exec_()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "gui":
        sys.exit(gui(sys.argv[2:]))
    sys.exit(cli(sys.argv[1:]))
