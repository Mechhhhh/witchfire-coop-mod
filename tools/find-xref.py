#!/usr/bin/env python3
"""Znajduje, KTORY KOD odwoluje sie do danego napisu — i co wola w poblizu.

Po co powstalo
--------------
Adresy funkcji zdobywalismy dotad przypadkiem: z logu UE4SS albo zgadujac.
Skonczylo sie to notatka `LoadMap 0x143BEAE50`, ktora okazala sie **falszywa**
(pod tym adresem stoi skok przez wskaznik prowadzacy poza modul, a prawdziwy
prolog jest 6 bajtow dalej). Wpisanie tam latki daloby awarie nie do powiazania
z przyczyna.

To narzedzie daje adresy w sposob POWTARZALNY. Kod silnika jest pelen
komunikatow diagnostycznych, ktore w wersji shipping sa skompilowane out jako
tekst, ale same literaly zostaja w binarce. Jesli wiemy, ze funkcja X loguje
"failed to Listen", to:
  1. znajdujemy ten napis w pamieci,
  2. szukamy instrukcji `lea rcx, [rip+X]`, ktora go laduje,
  3. patrzymy, co jest wolane TUZ PRZED nim — bo komunikat o bledzie stoi
     zaraz za sprawdzeniem wyniku tej wlasnie funkcji.
To daje adres funkcji, ktorej nazwy nigdzie nie ma.

Dlaczego z zywego procesu: to narzedzie czyta kod z pamieci dzialajacej gry.
Analize bez uruchomionej gry robi `obraz.py`, na obrazie pliku wykonywalnego
dostarczonym przez uzytkownika.

Uzycie
------
  find-xref.py <pid> "failed to Listen"
  find-xref.py <pid> "Listen" --waski        napis waski (ASCII), nie UTF-16
  find-xref.py <pid> "failed to Listen" --przed 60
"""
import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_common import Pamiec

import capstone


def zakres_modulu(pid):
    """Poczatek i koniec obszaru wykonywalnego glownego modulu gry."""
    poczatek = koniec = None
    with open(f"/proc/{pid}/maps") as f:
        for linia in f:
            if "Witchfire-Win64-Shipping.exe" not in linia:
                continue
            a, b = linia.split()[0].split("-")
            a, b = int(a, 16), int(b, 16)
            poczatek = a if poczatek is None else min(poczatek, a)
            koniec = b if koniec is None else max(koniec, b)
    return poczatek, koniec


def szukaj_napisu(m, poczatek, koniec, napis, waski):
    """Adresy, pod ktorymi lezy podany napis."""
    wzor = napis.encode("ascii") if waski else napis.encode("utf-16-le")
    trafienia = []
    krok = 0x100000
    a = poczatek
    while a < koniec:
        d = m.czytaj(a, min(krok, koniec - a))
        if d:
            start = 0
            while True:
                i = d.find(wzor, start)
                if i < 0:
                    break
                trafienia.append(a + i)
                start = i + 1
        a += krok
    return trafienia


def szukaj_lea(m, poczatek, koniec, cel):
    """Instrukcje `lea reg,[rip+disp]`, ktore ladowaly adres `cel`.

    Nie deasemblujemy calego modulu — to trwaloby minuty. Zamiast tego liczymy,
    jakie przesuniecie musialoby wystapic, i szukamy jego czterech bajtow.
    Kandydatow potwierdzamy dopiero deasemblacja."""
    trafienia = []
    krok = 0x100000
    a = poczatek
    while a < koniec:
        rozmiar = min(krok, koniec - a)
        d = m.czytaj(a, rozmiar)
        if d:
            # `lea r64,[rip+disp32]` ma 7 bajtow: REX 8D modrm=05 + disp32
            for i in range(len(d) - 7):
                if d[i] & 0xF0 != 0x40 or d[i + 1] != 0x8D or (d[i + 2] & 0xC7) != 0x05:
                    continue
                disp = struct.unpack_from("<i", d, i + 3)[0]
                if a + i + 7 + disp == cel:
                    trafienia.append(a + i)
        a += krok
    return trafienia


def main():
    ap = argparse.ArgumentParser(description="odwolania do napisu w kodzie gry")
    ap.add_argument("pid", type=int)
    ap.add_argument("napis")
    ap.add_argument("--waski", action="store_true", help="napis ASCII zamiast UTF-16")
    ap.add_argument("--przed", type=int, default=48,
                    help="ile bajtow kodu przed odwolaniem pokazac")
    a = ap.parse_args()

    m = Pamiec(a.pid)
    poczatek, koniec = zakres_modulu(a.pid)
    if not poczatek:
        print("nie znalazlem modulu gry w /proc/PID/maps")
        return 1
    print(f"modul: 0x{poczatek:X} .. 0x{koniec:X}")

    napisy = szukaj_napisu(m, poczatek, koniec, a.napis, a.waski)
    print(f"napis {a.napis!r}: {len(napisy)} wystapien")
    for s in napisy[:8]:
        print(f"  0x{s:X}")
    if not napisy:
        return 1

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for s in napisy[:4]:
        odw = szukaj_lea(m, poczatek, koniec, s)
        print(f"\n── kod ladujacy 0x{s:X}: {len(odw)} miejsc ──")
        for o in odw[:4]:
            print(f"\n  odwolanie pod 0x{o:X}, kod przed nim:")
            d = m.czytaj(o - a.przed, a.przed + 16)
            if not d:
                continue
            for ins in md.disasm(d, o - a.przed):
                znacznik = "  <-- tu" if ins.address == o else ""
                print(f"     0x{ins.address:X}  {ins.mnemonic:7s} {ins.op_str}{znacznik}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
