#!/usr/bin/env bash
# Sonda broni w petli, na OBU instancjach naraz.
#
# Po co: okno, w ktorym klient jest polaczony i zdrowy, trwalo w dotychczasowych
# przebiegach okolo minuty — za krotko, zeby zdazyc uruchomic pomiar recznie po
# zobaczeniu objawu. Skrypt startuje razem z klientem i probkuje sam, wiec nawet
# przebieg zakonczony awaria zostawia szereg czasowy zamiast jednego zdania.
#
# Uzycie: tools/pomiar-broni.sh <pid-hosta> <przebieg> [ile-probek] [odstep-s]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(dirname "$HERE")"
HOST_PID="${1:?podaj pid hosta}"
PRZEBIEG="${2:?podaj nazwe przebiegu}"
ILE="${3:-30}"
ODSTEP="${4:-10}"
KAT="$REPO/logs/$PRZEBIEG"
mkdir -p "$KAT"

# Format zwiezly: jeden wiersz na komponent, w obu instancjach, do JEDNEGO
# pliku. Poprzednia wersja pisala pelne wypisy do dwoch plikow i szereg czasowy
# byl w nich nie do odczytania — a najwazniejsze pytanie brzmi „kiedy ta wartosc
# sie zmienila", nie „jak wygladal pojedynczy pomiar".
SZEREG="$KAT/bron-szereg.txt"
: > "$SZEREG"

for i in $(seq 1 "$ILE"); do
    KLIENT=""
    for p in $(pgrep -x Witchfire-Win64); do
        [ "$p" = "$HOST_PID" ] || KLIENT="$p"
    done
    if kill -0 "$HOST_PID" 2>/dev/null; then
        python3 "$HERE/bron-lokalna.py" "$HOST_PID" --zwiezle 2>&1 \
            | sed 's/^/HOST   /' >> "$SZEREG"
    else
        echo "$(date +%H:%M:%S) HOST   PROCES ZNIKNAL" >> "$SZEREG"
    fi
    if [ -n "$KLIENT" ]; then
        python3 "$HERE/bron-lokalna.py" "$KLIENT" --zwiezle 2>&1 \
            | sed 's/^/KLIENT /' >> "$SZEREG"
    else
        echo "$(date +%H:%M:%S) KLIENT brak procesu" >> "$SZEREG"
    fi
    sleep "$ODSTEP"
done
echo "koniec serii: $SZEREG"
