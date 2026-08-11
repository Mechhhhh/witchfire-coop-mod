#!/usr/bin/env bash
# Zwraca PID instancji gry działającej w danym prefiksie Wine.
# Rozpoznanie po środowisku procesu, nie po kolejności pgrep — kolejność
# przestaje być wiarygodna, gdy któraś instancja padnie.
#
# Użycie: find-instance.sh compat1

set -uo pipefail
WANT="${1:?podaj nazwe prefiksu, np. compat1}"

# WF_PREFIX_ROOT — katalog, w ktorym leza prefiksy Proton obu instancji
# (ten sam, ktorego uzywa tools/launch-instance2.sh). Ustaw, jesli trzymasz
# je gdzie indziej: export WF_PREFIX_ROOT=/sciezka/do/prefiksow
PREFIX_ROOT="${WF_PREFIX_ROOT:-$HOME/.local/share/witchfire-mp}"

# Uwaga: Proton nadpisuje STEAM_COMPAT_DATA_PATH oryginalną ścieżką Steama,
# więc po niej rozpoznać się nie da. WINEPREFIX zachowuje to, co ustawiliśmy.
#
# Environ czytamy do zmiennej, a nie przez potok do `grep -q`: grep kończy
# pracę przy pierwszym trafieniu, `tr` dostaje SIGPIPE, a pipefail zamienia
# to w porażkę całego potoku — warunek nigdy nie byłby spełniony.
for pid in $(pgrep -x "Witchfire-Win64" 2>/dev/null); do
    env_dump=$(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null || true)
    case "$env_dump" in
        *"WINEPREFIX=${PREFIX_ROOT}/${WANT}/pfx"*)
            echo "$pid"
            exit 0
            ;;
    esac
done
exit 1
