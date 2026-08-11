#!/usr/bin/env python3
"""Deasembler ZYWEJ pamieci gry — z rozpoznawaniem, co dana funkcja wola.

Po co powstalo
--------------
`ue-funcs.py` podaje adres „natywny" funkcji, ale to NIE jest adres metody C++.
To `UFunction::Func`, czyli **przejsciowka skryptowa** (`execCos`) o sygnaturze
`void(UObject* Context, FFrame& Stack, void* Result)`. Zeby zawolac funkcje
z wlasnej DLL-ki, trzeba albo zbudowac `FFrame` (zmudne i lamliwe), albo wejsc
do przejsciowki i wyciagnac z niej adres prawdziwej metody — bo `execCos` robi
zwykle dokladnie jedno: rozpakowuje argumenty ze stosu skryptu i wola metode.

Drugi powod: to narzedzie pokazuje kod TAK, JAK LEZY W PAMIECI dzialajacej gry —
wiec widac tez nasze wlasne latki. Deasemblacje bez uruchomionej gry robi
`obraz.py fun`.

Uzycie
------
  ue-disasm.py <pid> 0x141C17730                 deasembluj do RET
  ue-disasm.py <pid> 0x141C17730 --wolania       same cele CALL (to zwykle wystarcza)
  ue-disasm.py <pid> 0x141C17730 --dlugosc 400
"""
import argparse
import os
import sys

import capstone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_common import Pamiec


def deasembluj(m, adres, dlugosc):
    dane = m.czytaj(adres, dlugosc)
    if not dane:
        return []
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    return list(md.disasm(dane, adres))


def main():
    ap = argparse.ArgumentParser(description="deasembler zywej pamieci")
    ap.add_argument("pid", type=int)
    ap.add_argument("adres")
    ap.add_argument("--dlugosc", type=int, default=256)
    ap.add_argument("--wolania", action="store_true", help="pokaz tylko cele CALL")
    a = ap.parse_args()

    m = Pamiec(a.pid)
    adres = int(a.adres, 16)
    instr = deasembluj(m, adres, a.dlugosc)
    if not instr:
        print(f"nie moge odczytac pamieci pod 0x{adres:X}")
        return 1

    cele = []
    for i in instr:
        if i.mnemonic == "call" and i.op_str.startswith("0x"):
            cele.append(int(i.op_str, 16))
        if not a.wolania:
            print(f"  0x{i.address:X}  {i.mnemonic:8s} {i.op_str}")
        if i.mnemonic in ("ret", "jmp") and not a.wolania:
            # `jmp` na koncu przejsciowki to ogon-wywolanie — tez konczy funkcje
            break

    if a.wolania or cele:
        print(f"\ncele CALL wewnatrz 0x{adres:X}:")
        if not cele:
            print("  (brak — funkcja nic nie wola, cala robota jest na miejscu)")
        for c in sorted(set(cele)):
            print(f"  0x{c:X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
