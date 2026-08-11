#!/usr/bin/env bash
# Zamyka wszystkie instancje gry i zwalnia klawisze modyfikatorów.
#
# Nie jest to kosmetyka: Witchfire w trybie okienkowym przechwytuje kursor
# i fokus, więc zostawiona działająca instancja psuje cały pulpit — menu
# systemowe otwiera się i natychmiast znika. Każdy test ma kończyć się tym
# skryptem, także gdy przerwie go błąd.

pkill -x "Witchfire-Win64" 2>/dev/null
sleep 2
pkill -9 -x "Witchfire-Win64" 2>/dev/null

# Osierocone procesy Protona i wineservery blokuja NASTEPNY start.
#
# Objaw jest mylacy: launcher przechodzi przez ProtonFixes i staje — exe w ogole
# sie nie pojawia, albo pojawia sie i wisi na czarnym ekranie bez logu UE4SS.
# Zdarzylo sie dwa razy z rzedu po `pkill -9` na grze (02:20 i 02:24), gdy dla
# jednego prefiksu zostaly DWA wineservery.
pkill -9 -f "pressure-vessel.*Witchfire" 2>/dev/null
pkill -9 -f "proton waitforexitandrun.*Witchfire" 2>/dev/null

# Raporter awarii UE. Witchfire nadaje mu tytul "Mission Disruption Report
# Needed", wiec na pierwszy rzut oka wyglada jak okno gry albo moda. Zostaje po
# kazdej awarii, trzyma otwarte okno i zabiera fokus — a przy dwoch instancjach
# zabranie fokusu ZATRZYMUJE ta, ktora go straci.
pkill -9 -f "CrashReportClient.exe" 2>/dev/null

# Tylko wineservery NASZYCH prefiksow testowych — nie ruszamy cudzych ani tych,
# ktorych Steam uzywa do innych gier.
for p in $(pgrep -f wineserver 2>/dev/null); do
    pfx=$(tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null | grep '^WINEPREFIX=' | cut -d= -f2-)
    case "$pfx" in
        *"/witchfire-mp/"*) kill -9 "$p" 2>/dev/null ;;
    esac
done

for k in Super_L Super_R Shift_L Shift_R Control_L Control_R Alt_L Alt_R Meta_L; do
    xdotool keyup "$k" 2>/dev/null
done

echo "instancje gry: $(pgrep -c -x 'Witchfire-Win64' 2>/dev/null || echo 0)"

# Kompozytory gamescope. UWAGA na nazwe procesu: to `gamescope-wl`, a NIE
# `gamescope` — przez co `pkill -x gamescope`, uzywane wczesniej w skryptach,
# nie trafialo w nic i po kazdym tescie zostawal wiszacy kompozytor.
pkill -x gamescope-wl 2>/dev/null
pkill -x gamescopereaper 2>/dev/null
pkill -x gamescope 2>/dev/null
