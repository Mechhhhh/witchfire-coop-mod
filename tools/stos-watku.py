#!/usr/bin/env python3
"""Stos ZYWEGO watku Win32 pod Wine — do zamrozen, nie do awarii.

Po co powstalo
--------------
Przy awarii dostajemy gotowy stos ze zrzutu. Przy ZAMROZENIU nie dostajemy nic:
proces zyje, plikow nie zostawia, a `eu-stack` i `gdb` rozwijaja tylko strone
uniksowa Wine i zatrzymuja sie na granicy — bo kod gry jest kompilowany bez
wskaznika ramki, a stos Win32 jest osobny od uniksowego.

Zamiast rozwijac stos porzadnie, robimy to, co przy zrzutach awaryjnych: bierzemy
SUROWY obszar stosu i wybieramy z niego wszystkie wartosci, ktore wygladaja na
adresy powrotu do modulu gry. Nie jest to prawdziwe rozwiniecie — beda falszywe
trafienia po starych ramkach — ale KOLEJNOSC jest zachowana, a nazwy funkcji
z `nazwij-ramke.py` mowia wprost, w czym watek stoi.

Skad wskaznik stosu: `/proc/<pid>/task/<tid>/syscall` podaje `sp` i `pc` w chwili
wejscia w wywolanie systemowe. Pod Wine `sp` wskazuje na stos Win32 watku
(niskie adresy, okolice 4 GB), czyli dokladnie na to, czego szukamy.

Uzycie:
    tools/stos-watku.py <pid>              # wszystkie watki silnika
    tools/stos-watku.py <pid> --tid 76748  # jeden watek
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_common import Pamiec

MODUL_OD = 0x140000000
MODUL_DO = 0x148000000       # z zapasem na nasze trampoliny pod 0x148000000


def sp_i_pc(pid, tid):
    try:
        with open(f"/proc/{pid}/task/{tid}/syscall") as f:
            czesci = f.read().split()
    except OSError:
        return None, None
    if len(czesci) < 3:
        return None, None
    try:
        return int(czesci[-2], 16), int(czesci[-1], 16)
    except ValueError:
        return None, None


def nazwa_watku(pid, tid):
    try:
        with open(f"/proc/{pid}/task/{tid}/comm") as f:
            return f.read().strip()
    except OSError:
        return "?"


def zbierz_funkcje(m):
    """Adres natywny -> nazwa, dla kazdej UFunction. Ten sam sposob co
    `nazwij-ramke.py`: nazywamy po adresach funkcji, NIE po sasiednich napisach."""
    from ue_common import UOBJ_OUTER_OFF
    funkcje = []
    for _, obj, klasa, _, _ in m.naglowki():
        if not klasa or m.nazwa_obiektu(klasa) != "Function":
            continue
        # UFunction::Func — wskaznik na kod natywny, na koncu struktury.
        for off in (0xB0, 0xA8, 0xB8):
            p = m.wskaznik(obj + off)
            if p and MODUL_OD <= p < MODUL_DO:
                wl = m.wskaznik(obj + UOBJ_OUTER_OFF)
                nazwa = m.nazwa_obiektu(obj)
                if wl:
                    nazwa = f"{m.nazwa_obiektu(wl)}::{nazwa}"
                funkcje.append((p, nazwa))
                break
    funkcje.sort()
    return funkcje


def nazwij(funkcje, adres, prog=0x4000):
    if not funkcje:
        return ""
    lo, hi = 0, len(funkcje) - 1
    naj = None
    while lo <= hi:
        sr = (lo + hi) // 2
        if funkcje[sr][0] <= adres:
            naj = funkcje[sr]
            lo = sr + 1
        else:
            hi = sr - 1
    if not naj or adres - naj[0] > prog:
        return ""
    return f"{naj[1]}+0x{adres - naj[0]:X}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pid", type=int)
    ap.add_argument("--tid", type=int, help="tylko ten watek")
    ap.add_argument("--bajtow", type=lambda s: int(s, 0), default=0x20000,
                    help="ile bajtow stosu przejrzec w gore od sp")
    ap.add_argument("--ile", type=int, default=40, help="ile ramek wypisac")
    ap.add_argument("--bez-nazw", action="store_true",
                    help="pomin refleksje (szybciej, ale bez nazw funkcji)")
    a = ap.parse_args()

    m = Pamiec(a.pid, buforuj=False)
    funkcje = [] if a.bez_nazw else zbierz_funkcje(m)
    if funkcje:
        print(f"znanych funkcji z refleksji: {len(funkcje)}")

    if a.tid:
        tidy = [a.tid]
    else:
        tidy = []
        for t in sorted(os.listdir(f"/proc/{a.pid}/task"), key=int):
            nm = nazwa_watku(a.pid, t)
            if nm.startswith(("Witchfire", "RenderThread", "RHIThread")):
                tidy.append(int(t))

    for tid in tidy:
        sp, pc = sp_i_pc(a.pid, tid)
        nm = nazwa_watku(a.pid, tid)
        print(f"\n══ tid={tid} {nm}  sp=0x{sp:X} pc=0x{pc:X}" if sp else
              f"\n══ tid={tid} {nm}  (brak sp — watek biegnie)")
        if not sp:
            continue
        # Stos konczy sie na granicy odwzorowania, wiec jeden duzy odczyt zwykle
        # sie nie udaje. Czytamy po stronie i konczymy na pierwszej nieczytelnej
        # — to jest wlasnie szczyt stosu.
        kawalki = []
        for off in range(0, a.bajtow, 0x1000):
            k = m.czytaj(sp + off, 0x1000)
            if not k:
                k = m.czytaj(sp + off, 0x800)
            if not k:
                break
            kawalki.append(k)
        dane = b"".join(kawalki)
        if len(dane) < 16:
            print("   nie udalo sie odczytac stosu")
            continue
        print(f"   (odczytano {len(dane)} B stosu)")
        wypisane = 0
        for off in range(0, len(dane) - 8, 8):
            (v,) = struct.unpack_from("<Q", dane, off)
            if not (MODUL_OD <= v < MODUL_DO):
                continue
            print(f"   +0x{off:05X}  0x{v:X}  {nazwij(funkcje, v)}")
            wypisane += 1
            if wypisane >= a.ile:
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
