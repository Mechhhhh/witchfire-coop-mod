#!/usr/bin/env bash
# Pilnuje przebiegu: wykrywa AWARIE i zamrozenia, i zapisuje kontekst.
#
# Po co
# -----
# Awaria konczy przebieg po cichu. Dotad dowiadywalem sie o niej od gracza
# („hosta zfreezowalo"), a potem trzeba bylo w tysiacach wierszy logu szukac,
# co dzialo sie tuz przed. Log rosnie miedzy przebiegami, wiec po godzinie ta
# sama robota kosztuje dwa razy tyle.
#
# Czuwak zapisuje moment awarii i OSTATNIE 200 wierszy logu sprzed niej —
# osobno, do katalogu przebiegu. To jest material, ktory potem realnie czyta sie
# zamiast calego logu.
#
# Rozroznia tez „zawiesilo sie" od „padlo": rozstrzyga swiezy zrzut w Crashes
# oraz to, czy proces dalej zjada takty procesora (obsluga wyjatku w UE potrafi
# wisiec i wygladac jak zamrozenie).
#
# Uzycie
# ------
#   tools/czuwak.sh <katalog-przebiegu> [minuty]
#   setsid nohup tools/czuwak.sh logs/t-dlugi 120 > /dev/null 2>&1 < /dev/null &
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
KAT="${1:?podaj katalog przebiegu}"; MINUTY="${2:-120}"
mkdir -p "$KAT"
WYJ="$KAT/czuwak.out"

PFX1="$HOME/.local/share/witchfire-mp/compat1/pfx/drive_c/users/steamuser/AppData/Local/Witchfire/Saved"
PFX2="$HOME/.local/share/witchfire-mp/compat2/pfx/drive_c/users/steamuser/AppData/Local/Witchfire/Saved"

ile_zrzutow() { ls -1 "$1/Crashes" 2>/dev/null | wc -l; }
takty() { awk '{print $14+$15}' "/proc/$1/stat" 2>/dev/null || echo ""; }

Z1=$(ile_zrzutow "$PFX1"); Z2=$(ile_zrzutow "$PFX2")
echo "$(date +%H:%M:%S) czuwak: start (zrzutow host=$Z1 klient=$Z2)" >> "$WYJ"

KONIEC=$(( $(date +%s) + MINUTY * 60 ))
declare -A OSTATNIE_TAKTY=()
declare -A ZAMROZONE=()

while [ "$(date +%s)" -lt "$KONIEC" ]; do
    sleep 10
    for STRONA in host klient; do
        [ "$STRONA" = host ] && { PFX="$PFX1"; STARE=$Z1; CMP=compat1; } \
                             || { PFX="$PFX2"; STARE=$Z2; CMP=compat2; }
        NOWE=$(ile_zrzutow "$PFX")
        if [ "$NOWE" -gt "$STARE" ]; then
            KIEDY=$(date +%H%M%S)
            echo "$(date +%H:%M:%S) czuwak: AWARIA $STRONA (zrzutow $STARE -> $NOWE)" >> "$WYJ"
            # Kontekst: ostatnie 200 wierszy logu TEJ strony, zanim urosnie dalej.
            tail -200 "$PFX/WFCoopProxy.log" > "$KAT/awaria-$STRONA-$KIEDY.log" 2>/dev/null
            NAJNOWSZY=$(ls -1dt "$PFX/Crashes"/*/ 2>/dev/null | head -1)
            if [ -n "$NAJNOWSZY" ]; then
                timeout 90 python3 "$HERE/read-crash-xml.py" "$NAJNOWSZY" \
                    > "$KAT/awaria-$STRONA-$KIEDY.raport" 2>&1
                echo "$(date +%H:%M:%S) czuwak:   raport -> awaria-$STRONA-$KIEDY.raport" >> "$WYJ"
            fi
            [ "$STRONA" = host ] && Z1=$NOWE || Z2=$NOWE
        fi

        # Zamrozenie: proces zyje, ale nie zjada taktow. Meldujemy RAZ.
        PID=$("$HERE/find-instance.sh" "$CMP" 2>/dev/null)
        [ -n "$PID" ] || continue
        T=$(takty "$PID")
        [ -n "$T" ] || continue
        POPRZ="${OSTATNIE_TAKTY[$STRONA]:-}"
        if [ -n "$POPRZ" ] && [ "$T" = "$POPRZ" ] && [ -z "${ZAMROZONE[$STRONA]:-}" ]; then
            echo "$(date +%H:%M:%S) czuwak: $STRONA nie zjada taktow od 10 s — zamrozenie albo wisząca obsługa wyjątku" >> "$WYJ"
            ZAMROZONE[$STRONA]=1
        elif [ "$T" != "$POPRZ" ]; then
            ZAMROZONE[$STRONA]=""
        fi
        OSTATNIE_TAKTY[$STRONA]=$T
    done
done
echo "$(date +%H:%M:%S) czuwak: koniec okna" >> "$WYJ"
