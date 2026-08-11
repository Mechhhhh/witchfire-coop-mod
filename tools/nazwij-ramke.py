#!/usr/bin/env python3
"""Nazywa adresy ze stosu awarii — po ADRESACH NATYWNYCH funkcji, nie po literalach.

Po co powstalo
--------------
`read-crash-xml.py` nazywa ramki, szukajac napisow lezacych obok adresu. To bylo
lepsze niz nic, ale nazywa SASIEDZTWO, a nie funkcje: napis moze nalezec do
zupelnie innej funkcji obok. Na tym omal nie zbudowalem calej hipotezy o awarii
("ramka #2 buduje sciezke profilu" bylo wnioskiem z literalu `.json`, a nie
faktem).

To narzedzie robi to porzadnie. Refleksja UE zna adres natywny KAZDEJ funkcji
(`UFunction::Func`), wiec:
  1. zbieramy adresy wszystkich funkcji z zywego procesu,
  2. sortujemy,
  3. dla kazdego adresu ze stosu bierzemy najwiekszy adres funkcji, ktory jest
     od niego mniejszy lub rowny.
To daje NAZWE funkcji zawierajacej dany adres — o ile ta funkcja jest widoczna
dla refleksji.

Ograniczenie, o ktorym trzeba pamietac: refleksja widzi tylko UFunction, czyli
funkcje wystawione do Blueprintow i skryptu. Czysty kod C++ silnika (jak
`FWeakObjectPtr::Get`) nie ma UFunction i nie zostanie nazwany — wtedy zamiast
zgadywac, narzedzie mowi wprost "brak dopasowania" i podaje odleglosc do
najblizszej znanej funkcji, zeby dalo sie ocenic, czy jestesmy w jej srodku,
czy zupelnie gdzie indziej.

Uzycie
------
  nazwij-ramke.py <pid> 0x1419F8EE9 0x141C16FFC
  nazwij-ramke.py <pid> --zrzut <katalog_awarii>
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_common import Pamiec

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "ue_funcs", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ue-funcs.py"))
_uf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_uf)


def zbierz_funkcje(pid):
    """[(adres_natywny, 'Klasa:Funkcja')] posortowane rosnaco."""
    m = Pamiec(pid)
    fn = _uf.Funkcje(m)
    if fn.so is None:
        return [], m
    wynik = []
    for _idx, o in m.obiekty():
        if m.nazwa_klasy(o) != "Function":
            continue
        nat = fn.natywna(o)
        if not nat or nat < 0x140000000 or nat > 0x147000000:
            continue
        wl = m.wskaznik(o + 0x20)
        wynik.append((nat, f"{m.nazwa_obiektu(wl) if wl else '?'}:{m.nazwa_obiektu(o)}"))
    wynik.sort()
    return wynik, m


def nazwij(funkcje, adres):
    """Najwieksza funkcja o adresie <= podanemu."""
    lo, hi = 0, len(funkcje) - 1
    trafiona = None
    while lo <= hi:
        sr = (lo + hi) // 2
        if funkcje[sr][0] <= adres:
            trafiona = funkcje[sr]
            lo = sr + 1
        else:
            hi = sr - 1
    return trafiona


def adresy_ze_zrzutu(katalog):
    plik = os.path.join(katalog, "CrashContext.runtime-xml")
    tresc = open(plik, errors="replace").read()
    return [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{9,16})", tresc)]


def main():
    ap = argparse.ArgumentParser(description="nazywa adresy po adresach natywnych UFunction")
    ap.add_argument("pid", type=int)
    ap.add_argument("adresy", nargs="*", help="adresy szesnastkowe")
    ap.add_argument("--zrzut", help="katalog awarii — wyciagnie adresy sam")
    ap.add_argument("--prog", type=int, default=0x20000,
                    help="powyzej tylu bajtow od poczatku funkcji uznajemy, ze to NIE ona")
    a = ap.parse_args()

    funkcje, m = zbierz_funkcje(a.pid)
    if not funkcje:
        print("nie udalo sie zebrac funkcji (uklad UStruct niewykryty?)")
        return 2
    print(f"znanych funkcji z adresem natywnym: {len(funkcje)}"
          f"  (zakres 0x{funkcje[0][0]:X} .. 0x{funkcje[-1][0]:X})\n")

    adresy = [int(x, 16) for x in a.adresy]
    if a.zrzut:
        adresy += adresy_ze_zrzutu(a.zrzut)
    if not adresy:
        print("podaj adresy albo --zrzut")
        return 1

    for adr in adresy:
        t = nazwij(funkcje, adr)
        if not t:
            print(f"  0x{adr:X}  — ponizej wszystkich znanych funkcji")
            continue
        odleglosc = adr - t[0]
        if odleglosc > a.prog:
            print(f"  0x{adr:X}  BRAK DOPASOWANIA "
                  f"(najblizsza znana {t[1]} lezy {odleglosc} B wczesniej — za daleko)")
        else:
            print(f"  0x{adr:X}  = {t[1]} + 0x{odleglosc:X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
