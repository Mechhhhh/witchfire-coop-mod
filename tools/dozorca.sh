#!/usr/bin/env bash
# Czeka, az host wejdzie na wyprawe, i SAM dolacza klienta oraz zbiera pomiar.
#
# Po co
# -----
# Gracz bywa zajety, a prosba „wejdz teraz na wyprawe" kosztuje przebieg za
# kazdym razem, gdy akurat nie patrzy. Zamiast pytac — nasluchujemy logu.
# Sygnal wejscia na wyprawe jest pewny i zmierzony: po starcie GWorld idzie
# `0x0 -> hub`, a wejscie na wyprawe to KOLEJNA zmiana, ze zrodla NIEZEROWEGO.
#
# Dzieki temu jedyne, co musi zrobic czlowiek, to kliknac CONTINUE i ruszyc na
# wyprawe — kiedy mu wygodnie. Reszta dzieje sie sama.
#
# Uzycie
# ------
#   tools/dozorca.sh <plik-wyjsciowy> [minuty-pomiaru]
#   tools/dozorca.sh /tmp/przebieg.out 10
#
# Uruchamiac ODCZEPIONY, inaczej ginie razem z powloka:
#   setsid nohup tools/dozorca.sh /tmp/przebieg.out > /dev/null 2>&1 < /dev/null &
#
# Wyniki:
#   <plik>          — przebieg dozorcy (kiedy co wykryl)
#   <plik>.pomiar   — wiersze logu odpowiadajace na pytanie przebiegu
#   <plik>.stamina  — stan obu graczy, probkowany w TEJ SAMEJ chwili
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(dirname "$HERE")"
S1="$HOME/.local/share/witchfire-mp/compat1/pfx/drive_c/users/steamuser/AppData/Local/Witchfire/Saved"
S2="$HOME/.local/share/witchfire-mp/compat2/pfx/drive_c/users/steamuser/AppData/Local/Witchfire/Saved"
LOG="$S1/WFCoopProxy.log"
WYJ="${1:?podaj plik wyjsciowy}"
MINUTY="${2:-10}"

[ -f "$LOG" ] || { echo "brak logu hosta: $LOG" >&2; exit 1; }

echo "$(date +%H:%M:%S) dozorca: czekam na wejscie hosta na wyprawe" >> "$WYJ"

# Sygnalem jest ZYWA POSTAC GRACZA w tablicy obiektow, a nie zmiana `GWorld`.
#
# Dwie wpadki jednego wieczoru nauczyly, ze `GWorld` jest tu dwuznaczny:
#   - `stary -> 0x0` przy starcie gry wyglada jak wyprawa (uruchomilo klienta
#     o 00:27, zanim host w ogole wyszedl z menu),
#   - a `0x0 -> nowy` BYWA wyprawa (gdy gracz kliknie CONTINUE od razu) albo
#     hubem (gdy nie kliknie) — i z samego logu tego nie odroznisz.
# Postac gracza istnieje tylko na wyprawie, wiec pytanie „czy juz?" ma
# jednoznaczna odpowiedz. Sprawdzamy rzadko, bo przejscie tablicy kosztuje.
while true; do
    sleep 15
    PH=$("$HERE/find-instance.sh" compat1 2>/dev/null)
    [ -n "$PH" ] || continue
    ILE=$(timeout 240 python3 "$HERE/rejestrator.py" --policz "$PH" 2>/dev/null)
    case "$ILE" in ''|*[!0-9]*) continue;; esac
    if [ "$ILE" -ge 1 ]; then
        echo "$(date +%H:%M:%S) dozorca: HOST NA WYPRAWIE (zywych postaci: $ILE)" >> "$WYJ"
        break
    fi
done

sleep 12                       # mapa musi sie ustabilizowac, zanim klient zapuka

echo 127.0.0.1 > "$S2/WFCoop_join_ip.txt"
echo "$(date +%H:%M:%S) dozorca: uruchamiam klienta" >> "$WYJ"
cd "$REPO" || exit 1
WF_GAMESCOPE=1 WF_PREFIX="$HOME/.local/share/witchfire-mp/compat2" WF_INJECT=proxy \
    nohup bash tools/launch-instance2.sh >> "$WYJ.klient" 2>&1 &

# Czarna skrzynka. Startuje dopiero, gdy klient ZDAZY sie polaczyc — inaczej
# rejestrator znalazlby jeden pionek zamiast dwoch i mierzyl polowe sprawy.
( sleep 150
  PH=$("$HERE/find-instance.sh" compat1 2>/dev/null)
  if [ -n "$PH" ]; then
      echo "$(date +%H:%M:%S) dozorca: startuje rejestrator (pid hosta $PH)" >> "$WYJ"
      python3 "$HERE/rejestrator.py" "$PH" "$WYJ.tsv" "$MINUTY" >> "$WYJ.rejestrator" 2>&1
      echo "$(date +%H:%M:%S) dozorca: rejestrator skonczyl" >> "$WYJ"
  fi
) &

echo "$(date +%H:%M:%S) dozorca: zbieram pomiar przez $MINUTY min" >> "$WYJ"
for i in $(seq 1 $((MINUTY * 6))); do
    sleep 10
    grep -hE 'CZAS:|TRYB:|AMUNICJA:|LIMIT: GetMaxSpeed|KANAL: odebrany stan' "$LOG" \
        | tail -80 > "$WYJ.pomiar"

    # Stan obu stron w TEJ SAMEJ chwili — inaczej porownanie nic nie znaczy.
    if [ $((i % 6)) -eq 0 ]; then
        PH=$("$HERE/find-instance.sh" compat1 2>/dev/null)
        PK=$("$HERE/find-instance.sh" compat2 2>/dev/null)
        if [ -n "$PH" ] && [ -n "$PK" ]; then
            {
                echo "--- $(date +%H:%M:%S) HOST (pid $PH)"
                timeout 90 python3 "$HERE/stan-gracza.py" --zwiezle "$PH" 2>&1 | tail -30
                echo "--- $(date +%H:%M:%S) KLIENT (pid $PK)"
                timeout 90 python3 "$HERE/stan-gracza.py" --zwiezle "$PK" 2>&1 | tail -30
            } >> "$WYJ.stamina"
        fi
    fi
done
echo "$(date +%H:%M:%S) dozorca: koniec okna pomiaru" >> "$WYJ"
