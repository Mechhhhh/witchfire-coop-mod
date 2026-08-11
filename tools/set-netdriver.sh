#!/usr/bin/env bash
# Podmienia NetDriver gry na czysty IpNetDriver (albo przywraca stan domyślny).
#
# Po co: domyślnie gra używa SteamNetDriver. Z opcją URL bIsLanMatch wchodzi on
# w tryb passthrough — hybrydę, w której host zawiesza wątek gry dwie sekundy
# po przyjęciu połączenia. IpNetDriver to zwykła ścieżka UDP, bez Steama.
#
# Nadpisania idą do Saved/Config/WindowsNoEditor/Engine.ini w prefiksie, bo
# `-ini:` z linii poleceń tu nie zadziała: UE rozcina wartości po przecinkach,
# a definicja NetDrivera sama zawiera przecinki.
#
# Użycie: set-netdriver.sh ip|default [compat1 compat2 ...]

set -uo pipefail

MODE="${1:?podaj tryb: ip albo default}"
shift || true
PREFIXES=("${@:-compat1 compat2}")
[ $# -eq 0 ] && PREFIXES=(compat1 compat2)

# WF_PREFIX_ROOT — katalog, w ktorym leza prefiksy Proton obu instancji
# (ten sam, ktorego uzywa tools/launch-instance2.sh).
PREFIX_ROOT="${WF_PREFIX_ROOT:-$HOME/.local/share/witchfire-mp}"

MARK_BEGIN="; === WFCoop BEGIN ==="
MARK_END="; === WFCoop END ==="

for p in "${PREFIXES[@]}"; do
    INI="$PREFIX_ROOT/$p/pfx/drive_c/users/steamuser/AppData/Local/Witchfire/Saved/Config/WindowsNoEditor/Engine.ini"
    if [ ! -f "$INI" ]; then
        echo "$p: brak $INI — pomijam"
        continue
    fi

    # Usuń poprzednie wpisy, żeby nie nawarstwiały się przy kolejnych
    # uruchomieniach. Nie da się polegać na komentarzach-znacznikach: gra
    # przepisuje Engine.ini przy starcie, zachowuje wpisy, a komentarze kasuje.
    # Dlatego czyścimy po treści — linie NetDriverDefinitions i osierocony
    # nagłówek sekcji, jeśli nic po nich nie zostało.
    python3 - "$INI" <<'PYEOF'
import sys
path = sys.argv[1]
lines = open(path, "r", newline="").read().splitlines()
out, i = [], 0
while i < len(lines):
    s = lines[i].strip()
    if s.startswith(";") and "WFCoop" in s:
        i += 1
        continue
    if "NetDriverDefinitions" in s:
        i += 1
        continue
    if s == "[/Script/Engine.GameEngine]":
        # Zajrzyj, czy w tej sekcji zostało cokolwiek prócz NetDriverDefinitions.
        j, keep = i + 1, False
        while j < len(lines) and not lines[j].strip().startswith("["):
            t = lines[j].strip()
            if t and not t.startswith(";") and "NetDriverDefinitions" not in t:
                keep = True
            j += 1
        if not keep:
            i += 1
            continue
    out.append(lines[i])
    i += 1
while out and not out[-1].strip():
    out.pop()
open(path, "w", newline="").write("\r\n".join(out) + "\r\n")
PYEOF

    if [ "$MODE" = "ip" ]; then
        {
            printf '\r\n%s\r\n' "$MARK_BEGIN"
            printf '[/Script/Engine.GameEngine]\r\n'
            printf '!NetDriverDefinitions=ClearArray\r\n'
            # Format to Modul.Klasa, BEZ przedrostka /Script/ — z nim UE nie
            # rozwiazuje klasy i cicho zostaje przy dotychczasowym driverze.
            printf '+NetDriverDefinitions=(DefName="GameNetDriver",DriverClassName="OnlineSubsystemUtils.IpNetDriver",DriverClassNameFallback="OnlineSubsystemUtils.IpNetDriver")\r\n'
            printf '%s\r\n' "$MARK_END"
        } >> "$INI"
        echo "$p: ustawiono IpNetDriver"
    else
        echo "$p: przywrocono domyslny NetDriver"
    fi
done
