#!/bin/bash
# Legt die vier Befehle schach-brett, schach-stellung, schach-zug, schach-neu in ~/.local/bin an.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.local/bin"
for b in brett stellung zug neu modus; do
  printf '#!/bin/bash\nexec python3 "%s/schachbrett.py" %s "$@"\n' "$DIR" "$b" > "$HOME/.local/bin/schach-$b"
  chmod +x "$HOME/.local/bin/schach-$b"
done
echo "Fertig. Befehle: schach-brett, schach-stellung, schach-zug, schach-neu, schach-modus (~/.local/bin muss im PATH sein)."
