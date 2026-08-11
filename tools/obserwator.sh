#!/usr/bin/env bash
# Stały obserwator: startuje SAM, gdy pojawi się gra, i nagrywa całą sesję.
#
# Po co
# -----
# Dotad kazdy pomiar zaczynal sie od „powiedz mi, ze grasz, to cos ustawie".
# Skutek: gdy gracz na cos trafial, danych z tej chwili juz nie bylo i trzeba
# bylo prosic o powtorke. Ten skrypt odwraca kolejnosc — chodzi w tle, wykrywa
# uruchomienie gry (kazdej: czystej albo z modem) i od razu zaczyna zapisywac.
#
# Kiedy gracz mowi „tu sie zepsulo", material z tej chwili juz lezy na dysku.
#
# Co zbiera dla KAZDEJ sesji, do `logs/sesje/<data>-<rodzaj>/`:
#   szereg.tsv   — szereg czasowy z pamieci (tryb ruchu, warunki, atrybuty)
#   proxy.log    — kopia logu biblioteki obcieta do TEJ sesji
#   stan.txt     — z czego sesja sie skladala: prefiks, markery, suma biblioteki
#   awaria-*     — kontekst awarii, jesli byla (przez `czuwak.sh`)
#
# Nic nie zapisuje do pamieci gry. Same odczyty.
#
# Uzycie
# ------
#   setsid nohup tools/obserwator.sh > /dev/null 2>&1 < /dev/null &
#   tools/obserwator.sh --stan        # co teraz widzi
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(dirname "$HERE")"
SESJE="$REPO/logs/sesje"; mkdir -p "$SESJE"
DZIENNIK="$SESJE/obserwator.log"

if [ "${1:-}" = "--stan" ]; then
    echo "== obserwator =="
    pgrep -f 'tools/obserwator.sh' | grep -qv $$ && echo "dziala" || echo "NIE dziala"
    echo; echo "== ostatnie sesje =="
    ls -1dt "$SESJE"/*/ 2>/dev/null | head -5
    echo; echo "== ostatnie wpisy =="
    tail -12 "$DZIENNIK" 2>/dev/null
    exit 0
fi

mow() { echo "$(date '+%m-%d %H:%M:%S') $*" >> "$DZIENNIK"; }

znajdz_pid() {
    for c in /proc/[0-9]*/comm; do
        [ "$(cat "$c" 2>/dev/null)" = "Witchfire-Win64" ] || continue
        echo "${c#/proc/}" | cut -d/ -f1
        return 0
    done
    return 1
}

mow "obserwator wstal"

while true; do
    PID=$(znajdz_pid) || { sleep 15; continue; }

    # Czym jest ta instancja: nasza (z modem) czy czysta ze Steama.
    ENV=$(tr '\0' '\n' < "/proc/$PID/environ" 2>/dev/null || true)
    case "$ENV" in
        *witchfire-mp/compat1*) RODZAJ=host;   PFX="$HOME/.local/share/witchfire-mp/compat1" ;;
        *witchfire-mp/compat2*) RODZAJ=klient; PFX="$HOME/.local/share/witchfire-mp/compat2" ;;
        *)                      RODZAJ=czysta; PFX="" ;;
    esac
    KAT="$SESJE/$(date +%Y%m%d-%H%M%S)-$RODZAJ"; mkdir -p "$KAT"
    mow "sesja $RODZAJ (pid $PID) -> $(basename "$KAT")"

    # Z czego ta sesja sie skladala — inaczej za tydzien nie odroznisz przebiegow.
    {
        echo "pid=$PID rodzaj=$RODZAJ start=$(date '+%F %T')"
        [ -n "$PFX" ] && echo "prefiks=$PFX"
        echo "biblioteka: $(md5sum /mnt/gry/SteamLibrary/steamapps/common/Witchfire/Witchfire/Binaries/Win64/xinput1_3.dll 2>/dev/null | cut -c1-8)"
        if [ -n "$PFX" ]; then
            echo "markery:"
            ls -1 "$PFX/pfx/drive_c/users/steamuser/AppData/Local/Witchfire/Saved"/WFCoop_*.txt 2>/dev/null \
                | xargs -n1 basename 2>/dev/null | sed 's/^/  /'
        fi
    } > "$KAT/stan.txt"

    LOG=""
    [ -n "$PFX" ] && LOG="$PFX/pfx/drive_c/users/steamuser/AppData/Local/Witchfire/Saved/WFCoopProxy.log"
    OD=0; [ -n "$LOG" ] && [ -f "$LOG" ] && OD=$(wc -l < "$LOG")

    # Czuwak od awarii — tylko dla naszych instancji, bo czysta nie ma naszego logu.
    if [ -n "$PFX" ]; then
        setsid nohup bash "$HERE/czuwak.sh" "$KAT" 600 > /dev/null 2>&1 < /dev/null &
    fi

    # Rejestrator startuje dopiero, gdy istnieje POSTAC — czyli gdy gracz jest
    # na wyprawie. W menu nie ma czego probkowac.
    ( for i in $(seq 1 240); do
        kill -0 "$PID" 2>/dev/null || break
        ILE=$(timeout 240 python3 "$HERE/rejestrator.py" --policz "$PID" 2>/dev/null)
        case "$ILE" in ''|*[!0-9]*) sleep 15; continue;; esac
        if [ "$ILE" -ge 1 ]; then
            mow "  postac jest ($ILE) — rejestruje"
            python3 "$HERE/rejestrator.py" "$PID" "$KAT/szereg.tsv" 600 \
                >> "$KAT/rejestrator.out" 2>&1
            break
        fi
        sleep 15
      done ) &
    REJ=$!

    # Czekamy na koniec gry.
    while kill -0 "$PID" 2>/dev/null; do sleep 10; done
    mow "  sesja skonczona (pid $PID zniknal)"
    kill "$REJ" 2>/dev/null

    # Kopia logu obcieta do TEJ sesji — log biblioteki rosnie miedzy przebiegami
    # i szukanie w nim po fakcie kosztuje wiecej niz sam pomiar.
    if [ -n "$LOG" ] && [ -f "$LOG" ]; then
        tail -n +"$((OD + 1))" "$LOG" > "$KAT/proxy.log" 2>/dev/null
        mow "  log sesji: $(wc -l < "$KAT/proxy.log") wierszy"
    fi
    sleep 10
done
