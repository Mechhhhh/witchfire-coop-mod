#!/usr/bin/env bash
# Zrzut ekranu z NAZWA, ktora sama siebie tlumaczy.
#
# Po co: zrzuty ladowaly w katalogu tymczasowym jako `p1.png`, `q1.png`,
# `look_a.png`. Przy kilkudziesieciu przebiegach nie da sie po takiej nazwie
# powiedziec, ktora to instancja ani w jakim byla stanie — a raz doprowadzilo
# to do pomylenia instancji ZDROWEJ z zamrozona i uniewaznilo caly pomiar.
#
# Nazwa pliku zawiera wszystko, co potrzebne do odczytania go po tygodniu:
#   <przebieg>/<HHMMSS>-<instancja>-<faza>.png
#
# DLACZEGO TO BYLO ZEPSUTE (i czemu warto o tym pamietac)
# -------------------------------------------------------
# Poprzednia wersja szukala okna przez `xdotool getwindowpid`. Nie dziala to
# tutaj z dwoch powodow naraz:
#   1. Sesja to Wayland (Hyprland) — `xdotool` widzi tylko okna X11, a okna gry
#      nie ma wsrod nich w ogole.
#   2. Nawet gdyby byla: pod gamescope okno NIE NALEZY do procesu gry. Gra
#      renderuje do wlasnego kompozytora, a okno na pulpicie nalezy do procesu
#      `gamescope-wl`, ktory jest jej DZIADKIEM (gra <- pv-adverb <- srt-bwrap
#      <- gamescopereaper <- gamescope-wl).
# Stad: idziemy w gore drzewa procesow od PID gry, az znajdziemy przodka, ktory
# ma okno w `hyprctl clients`, i zrzucamy jego geometrie przez `grim`.
#
# Uzycie:
#   tools/zrzut.sh <przebieg> <host|klient> <faza>
#   tools/zrzut.sh t3-hub host przed-dolaczeniem

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(dirname "$HERE")"
PRZEBIEG="${1:?podaj nazwe przebiegu}"; KTO="${2:?host albo klient}"; FAZA="${3:?opis fazy}"

case "$KTO" in
    host)   PFX=compat1 ;;
    klient) PFX=compat2 ;;
    *) echo "drugi argument: host albo klient" >&2; exit 1 ;;
esac

PID=$("$HERE/find-instance.sh" "$PFX" 2>/dev/null)
[ -n "$PID" ] || { echo "nie znalazlem instancji $KTO ($PFX)" >&2; exit 1; }

# Geometria okna przodka, ktory faktycznie ma okno na pulpicie.
GEO=$(python3 - "$PID" <<'PY'
import json, subprocess, sys
pid = int(sys.argv[1])

# lancuch przodkow procesu gry
rodzice, p = [], pid
for _ in range(10):
    rodzice.append(p)
    try:
        with open(f"/proc/{p}/stat") as f:
            p = int(f.read().rsplit(")", 1)[1].split()[1])
    except Exception:
        break
    if p <= 1:
        break

try:
    okna = json.loads(subprocess.run(["hyprctl", "clients", "-j"],
                                     capture_output=True, text=True).stdout)
except Exception:
    sys.exit(1)
for o in okna:
    if o.get("pid") in rodzice:
        x, y = o["at"]
        w, h = o["size"]
        print(f"{x},{y} {w}x{h}")
        sys.exit(0)
sys.exit(1)
PY
) || { echo "nie znalazlem okna dla instancji $KTO (PID gry $PID)" >&2; exit 1; }

DIR="$REPO/logs/$PRZEBIEG/zrzuty"; mkdir -p "$DIR"
PLIK="$DIR/$(date +%H%M%S)-$KTO-$FAZA.png"
grim -g "$GEO" "$PLIK" 2>/dev/null || { echo "grim nie powiodl sie ($GEO)" >&2; exit 1; }

# Kontekst zapisujemy OBOK zrzutu, bo sam obraz nie mowi, co wtedy mierzylismy.
{
  echo "$(date +%H:%M:%S) | $KTO | $FAZA | okno $GEO"
  echo "  PID=$PID  CPU=$(ps -o pcpu= -p "$PID" | tr -d ' ')%"
  total=$(ps -L -o tid= -p "$PID" 2>/dev/null | wc -l)
  czek=$(ps -L -o wchan= -p "$PID" 2>/dev/null | grep -cv '^-\?$')
  echo "  watki czekajace: $czek z $total   (zdrowa instancja: bliskie 0)"
} >> "$DIR/opis.txt"

echo "$PLIK"
