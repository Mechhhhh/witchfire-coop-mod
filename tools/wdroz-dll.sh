#!/usr/bin/env bash
# Buduje proxy-DLL i wstawia ja do katalogu gry.
#
# Po co osobny skrypt: DLL trafia do gry KOPIA (nie dowiazaniem — Wine
# otwiera plik na wylacznosc, gdy gra dziala, wiec podmiana w locie musi byc
# swiadoma i po zamknieciu instancji). Dwa razy zdarzylo sie uruchomienie
# przebiegu na STAREJ bibliotece, bo krok kopiowania zrobiono z pamieci
# i pominieto. Skrypt konczy sie porownaniem sum kontrolnych — jesli sie nie
# zgadzaja, przebieg nie ma sensu.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
# WF_GAME_DIR — katalog instalacyjny gry (ten z podkatalogiem
# Witchfire/Binaries/Win64). Ustaw, jesli gra nie stoi w domyslnej
# bibliotece Steama.
GAME_DIR="${WF_GAME_DIR:-$HOME/.local/share/Steam/steamapps/common/Witchfire}"
GAME_WIN64="$GAME_DIR/Witchfire/Binaries/Win64"

# Sciezka domyslna to tylko zgadywanka (domyslna biblioteka Steama). Bez tego
# sprawdzenia bledna sciezka konczyla sie komunikatem `cp`, ktory nie mowi,
# ktora zmienna ustawic.
if [ ! -d "$GAME_WIN64" ]; then
    echo "nie ma katalogu gry: $GAME_WIN64" >&2
    echo "ustaw WF_GAME_DIR na katalog instalacyjny Witchfire, np.:" >&2
    echo "  export WF_GAME_DIR=/sciezka/do/SteamLibrary/steamapps/common/Witchfire" >&2
    exit 1
fi

if pgrep -x "Witchfire-Win64" >/dev/null 2>&1; then
    echo "gra DZIALA — zamknij ja (tools/stop.sh) przed podmiana biblioteki" >&2
    exit 1
fi

"$REPO/src/proxy-dll/build.sh" >/dev/null
cp "$REPO/src/proxy-dll/build/xinput1_3.dll" "$GAME_WIN64/xinput1_3.dll"

a=$(md5sum < "$REPO/src/proxy-dll/build/xinput1_3.dll" | cut -d' ' -f1)
b=$(md5sum < "$GAME_WIN64/xinput1_3.dll" | cut -d' ' -f1)
[ "$a" = "$b" ] || { echo "NIEZGODNE sumy kontrolne: $a vs $b" >&2; exit 1; }
echo "wdrozone: $GAME_WIN64/xinput1_3.dll  md5=$a"
