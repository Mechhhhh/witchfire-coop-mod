#!/usr/bin/env bash
# Uruchamia DRUGĄ instancję Witchfire, omijając Steam UI (które blokuje
# uruchomienie tej samej gry dwa razy). Używa osobnego prefiksu Wine,
# żeby nie gryźć się o pfx.lock i configi z instancją nr 1.
#
# Steam MUSI działać w tle — bez uruchomionego klienta Steam gra nie startuje.

set -euo pipefail

# WF_GAME_DIR — katalog instalacyjny gry, czyli ten, w ktorym lezy podkatalog
# Witchfire/Binaries/Win64. Ustaw, jesli gra nie stoi w domyslnej bibliotece
# Steama, np.:
#   export WF_GAME_DIR=/mnt/dysk/SteamLibrary/steamapps/common/Witchfire
GAME_DIR="${WF_GAME_DIR:-$HOME/.local/share/Steam/steamapps/common/Witchfire}"
EXE="$GAME_DIR/Witchfire/Binaries/Win64/Witchfire-Win64-Shipping.exe"
PROTON="${PROTON_TOOL:-/usr/share/steam/compatibilitytools.d/proton-cachyos-slr/proton}"
# proton-cachyos wymaga Pythona 3.11+ (`from typing import Self`), więc runtime
# "sniper" (python 3.9) odpada — trzeba steamrt4.
# Runtime szukany domyslnie w tej samej bibliotece Steama, co gra.
SLR="${SLR_ENTRY:-$(dirname "$GAME_DIR")/SteamLinuxRuntime_4/_v2-entry-point}"

# Sciezki domyslne to zgadywanka (domyslna biblioteka Steama). Bez sprawdzenia
# blad wychodzil dopiero z wnetrza Protona i nie mowil, ktora zmienna ustawic.
if [ ! -f "$EXE" ]; then
    echo "nie ma pliku gry: $EXE" >&2
    echo "ustaw WF_GAME_DIR na katalog instalacyjny Witchfire, np.:" >&2
    echo "  export WF_GAME_DIR=/sciezka/do/SteamLibrary/steamapps/common/Witchfire" >&2
    exit 1
fi
if [ ! -x "$SLR" ]; then
    echo "nie ma Steam Linux Runtime: $SLR" >&2
    echo "ustaw SLR_ENTRY na _v2-entry-point runtime'u steamrt4" >&2
    exit 1
fi

export STEAM_COMPAT_CLIENT_INSTALL_PATH="$HOME/.local/share/Steam"
# WF_PREFIX_ROOT — katalog, w ktorym trzymamy prefiksy Proton obu instancji.
export STEAM_COMPAT_DATA_PATH="${WF_PREFIX:-${WF_PREFIX_ROOT:-$HOME/.local/share/witchfire-mp}/compat2}"
# Punkt montowania, ktory Proton ma udostepnic grze — potrzebny, gdy gra lezy
# poza katalogiem domowym. Domyslnie sam katalog gry; przy osobnym dysku
# ustaw WF_COMPAT_MOUNTS na punkt montowania, np. /mnt/dysk.
export STEAM_COMPAT_MOUNTS="${WF_COMPAT_MOUNTS:-$GAME_DIR}"
export STEAM_COMPAT_APP_ID=3156770
export SteamAppId=3156770
export SteamGameId=3156770
# PROTON_LOG=1 domyślnie WYŁĄCZONE i to nie jest drobiazg: włącza w Wine
# +seh, przez co każdy wyjątek C++ generuje setki linii trace:unwind. UE przy
# inicjalizacji sieci rzuca ich tyle, że gra praktycznie staje — wyglądało to
# jak zawieszenie hosta po wejściu w tryb listen. Dodatkowo obie instancje
# pisałyby do tego samego $HOME/steam-<appid>.log i nadpisywały się nawzajem.
# Włącz przez WF_PROTON_LOG=1 tylko wtedy, gdy naprawdę chcesz ten szum.
if [ "${WF_PROTON_LOG:-0}" = "1" ]; then
    export PROTON_LOG=1
fi

# WF_NO_FSYNC=1 wylacza szybka synchronizacje Wine (fsync/esync) dla TEJ
# instancji. Po co: klient zamarza po dolaczeniu, a pomiar z probka kontrolna
# (host zdrowy obok) pokazal, ze ZADEN watek silnika nie wykonuje ani jednego
# cyklu — GameThread stoi na stalym adresie futex, podczas gdy u hosta ten sam
# watek pracuje (+317 tick / 4 s). Wszystko inne u klienta jest poprawne: siec
# zadziala, poziomy sie zaladowaly, aktory i postac doszly. Czyli podejrzanym
# jest sama synchronizacja, a nie logika co-opu.
#
# Ten Proton uzywa FSYNC (nie ntsync — `ntsync_char_ioctl` w `wchan` to warstwa
# nizej). Skrypt protona rozpoznaje PROTON_NO_FSYNC i PROTON_NO_ESYNC; ustawiamy
# oba, bo wylaczenie samego fsync przelacza Wine na esync, a nie na serwer.
if [ "${WF_NO_FSYNC:-0}" = "1" ]; then
    export PROTON_NO_FSYNC=1
    export PROTON_NO_ESYNC=1
fi

# Celowany podgląd wyjątków: WINEDEBUG=+seh loguje same wyjątki wraz z adresem,
# bez lawiny trace:unwind, która przy PROTON_LOG=1 zabijała wydajność.
# Użycie: WF_WINEDEBUG=+seh ./launch-instance2.sh
if [ -n "${WF_WINEDEBUG:-}" ]; then
    export WINEDEBUG="$WF_WINEDEBUG"
fi

# UE4SS wchodzi jako proxy dwmapi.dll (gra importuje dwmapi). Pod Wine trzeba
# jawnie powiedzieć, żeby wziął naszą natywną DLL zamiast wbudowanej: n,b.
#
# WF_NO_UE4SS=1 pomija to nadpisanie, czyli uruchamia grę CAŁKIEM bez UE4SS.
# Potrzebne jako test kontrolny: klient ginie sekundę po wejściu do świata
# hosta niezależnie od wszystkiego, co możemy przestawić w modzie, a UE4SS
# haczy silnik na wskroś (GUObjectArray, FName, ProcessEvent). Bez niego
# klient nie ma jak sam dołączyć — od tego jest URL w linii poleceń niżej.
#
# WF_INJECT wybiera, KTO wchodzi do tej instancji:
#   ue4ss (domyslnie) — dwmapi natywne (UE4SS), xinput1_3 wbudowane
#   proxy             — xinput1_3 natywne (nasza DLL), dwmapi wbudowane
#
# Dlaczego xinput1_3, a nie version: Wine UBIJA proces, gdy ktokolwiek siegnie
# po funkcje, ktorej podrobka nie eksportuje ("unimplemented function
# VERSION.dll.GetFileVersionInfoSizeExW, aborting"). version.dll ma 17 funkcji,
# czesc z osmioma argumentami — przekierowanie kazdej po sygnaturze jest
# ryzykowne. XInput ma osiem, a jego semantyka pozwala uczciwie odpowiedziec
# "brak kontrolera", wiec nie trzeba przekierowywac NICZEGO.
#   brak              — nic nie wchodzi
#
# Po co dwa warianty: obie instancje dziela katalog gry, wiec jeden plik nie
# moze nalezec naraz do UE4SS i do nas. WINEDLLOVERRIDES dziala jednak PER
# PROCES, wiec host moze miec UE4SS, a klient nasza DLL — i o to chodzi w M4.
case "${WF_INJECT:-ue4ss}" in
    ue4ss) OV="dwmapi=n,b;xinput1_3=b" ;;
    proxy) OV="xinput1_3=n,b;dwmapi=b" ;;
    brak|none) OV="" ;;
    *) echo "WF_INJECT: nieznana wartosc '${WF_INJECT}'" >&2; exit 1 ;;
esac
# WF_NO_UE4SS=1 zostaje dla zgodnosci ze starszymi wywolaniami.
[ "${WF_NO_UE4SS:-0}" = "1" ] && OV=""
[ -n "$OV" ] && export WINEDLLOVERRIDES="${OV}${WINEDLLOVERRIDES:+;$WINEDLLOVERRIDES}"

# Okno mniejsze i bez pełnego ekranu, żeby dało się patrzeć na dwie instancje naraz.
GAME_ARGS=(-windowed -ResX=1280 -ResY=720 -nosplash -log)

# WF_URL=127.0.0.1 podaje adres jako URL startowy. Silnik UE traktuje pierwszy
# argument niebędący przełącznikiem jako URL mapy albo serwera, więc gra łączy
# się sama, bez moda i bez komend konsoli (te w shippingu i tak są martwe).
# Musi iść PRZED przełącznikami, bo parser bierze pierwszy taki token.
if [ -n "${WF_URL:-}" ]; then
    GAME_ARGS=("$WF_URL" "${GAME_ARGS[@]}")
fi

# WF_GAMESCOPE=1 uruchamia instancję we WŁASNYM kompozytorze.
#
# Po co: gra pauzuje się przy utracie fokusu okna, a **jedna** taka utrata psuje
# sterowanie trwale — nie pomaga nawet ręczne kliknięcie RESUME (sprawdzone przez
# użytkownika). Przy dwóch oknach na jednym pulpicie to jest nie do obejścia:
# fokus ma zawsze najwyżej jedno z nich, więc druga instancja jest z definicji
# zepsuta. W gamescope każda instancja ma własny kompozytor i cały czas uważa,
# że jest na wierzchu — dopiero to pozwala testować dwóch graczy naraz.
# ODPIECIE OD POWLOKI — `setsid`, nie samo `nohup`.
#
# Powod, znaleziony pomiarem 2026-08-10: `gamescopereaper` zabija swoje dzieci,
# gdy ginie jego proces NADRZEDNY. Przy uruchamianiu gry z narzedzia przerwanie
# wywolania (albo zwykle zakonczenie powloki) ubijalo cala gre:
#   [gamescopereaper] Parent of gamescopereaper was killed. Killing children.
#   [gamescope] Primary child shut down!
# Wygladalo to jak ciche padniecie gry BEZ zrzutu awaryjnego — i przez chwile
# szukalem w grze bledu, ktorego tam nie bylo. `nohup` nie wystarcza, bo chroni
# tylko przed SIGHUP, a tu ginie caly rodzic. `setsid` daje nowa sesje i grupe
# procesow, wiec gra przezywa zamkniecie powloki, ktora ja uruchomila.
# --force-grab-cursor / -g: bez nich kursor UCIEKA z okna gry.
#
# Objaw zgloszony przez gracza: kliknięcie lewym w oknie gry przerzuca myszkę
# na środek drugiego monitora — czyli nie da się nawet trafić w CONTINUE, a to
# jedyny krok, którego automat wykonać nie może. Powod: w menu gra nie prosi
# o blokade wskaznika, wiec gamescope go nie przytrzymuje, a wlasne wysrodkowanie
# kursora przez gre laduje poza jej oknem. `--force-grab-cursor` wlacza tryb
# wzgledny NA STALE, niezaleznie od tego, czy gra akurat chowa kursor.
# WF_NO_GRAB=1 wylacza to z powrotem, gdyby przeszkadzalo w menu.
if [ "${WF_GAMESCOPE:-0}" = "1" ]; then
    GS_ARGS=(-W "${WF_W:-1280}" -H "${WF_H:-720}")
    if [ "${WF_NO_GRAB:-0}" != "1" ]; then
        GS_ARGS+=(--force-grab-cursor -g)
    fi
    exec setsid gamescope "${GS_ARGS[@]}" -- \
         "$SLR" --verb=waitforexitandrun -- \
         "$PROTON" waitforexitandrun "$EXE" "${GAME_ARGS[@]}" "$@"
fi

exec setsid "$SLR" --verb=waitforexitandrun -- \
     "$PROTON" waitforexitandrun "$EXE" "${GAME_ARGS[@]}" "$@"
