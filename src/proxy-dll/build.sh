#!/usr/bin/env bash
# Buduje WFCoopProxy (dwmapi.dll) krzyzowo pod Windows.
#
# Pelne -static jest KONIECZNE. Sama para -static-libgcc/-static-libstdc++ nie
# obejmuje libwinpthread-1.dll, ktorej w prefiksie Wine nie ma — ladowarka
# odrzucala wtedy nasza biblioteke i gra w ogole nie wstawala, bez zadnego
# komunikatu (sprawdzone 02:06: zero procesow, zero logu).
#
# -municode wyrzucone: dotyczy punktu wejscia programu (wmain), a nie DLL.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/build}"
mkdir -p "$OUT"

# Budujemy DWA warianty tej samej biblioteki. Powod: obie instancje dziela
# katalog gry, wiec jeden plik nie moze nalezec naraz do UE4SS i do nas.
# WINEDLLOVERRIDES dziala PER PROCES, wiec host bierze dwmapi natywne (UE4SS),
# a klient xinput1_3 natywne (my) — i kazdy dostaje dokladnie jeden wstrzykiwacz.
# (Dlaczego xinput1_3, a nie version: patrz komentarz w tools/launch-instance2.sh.)
build() {
    local name="$1"; shift
    x86_64-w64-mingw32-g++ \
        -shared -O2 \
        -DUNICODE -D_UNICODE "$@" \
        -static -static-libgcc -static-libstdc++ \
        -Wall -Wextra -Wno-cast-function-type \
        -o "$OUT/$name.dll" \
        "$HERE/dllmain.cpp" "$HERE/$name.def"
    echo "zbudowano: $OUT/$name.dll"
    x86_64-w64-mingw32-nm -g --defined-only "$OUT/$name.dll" | awk '{print "    "$3}'
}

build dwmapi
build xinput1_3 -DWFCOOP_AS_XINPUT

echo "--- zaleznosci (nie moze byc libwinpthread ani libgcc) ---"
x86_64-w64-mingw32-objdump -p "$OUT/xinput1_3.dll" | grep "DLL Name:" | sort -u
