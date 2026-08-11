#!/usr/bin/env python3
"""Ktore metody wirtualne gra NADPISALA — przez porownanie tablic metod.

Po co powstalo
--------------
Gdy wiadomo juz, ze blad siedzi w klasie gry, a nie w silniku, deasemblowanie
„od poczatku klasy" jest strzelaniem na oslep: `DimensionMovementComponent`
dziedziczy po `UCharacterMovementComponent`, ktory ma kilkaset metod wirtualnych.
Interesuja nas wylacznie te, ktore gra PODMIENILA — bo tylko tam moze byc jej
wlasny warunek.

Jak: wzorzec klasy (CDO) ma w pierwszych osmiu bajtach wskaznik na tablice metod.
Bierzemy CDO klasy pochodnej i bazowej, czytamy obie tablice i porownujemy wpis
po wpisie. Rozne wpisy to nadpisania — i tylko one ida do deasemblacji.

Numer gniazda nie mowi, KTORA to metoda (brak symboli), ale daje krotka liste
adresow zamiast calego modulu. Nazwy trzeba dopiero ustalic po tresci kodu.

Uzycie:
    tools/vtable-diff.py <pid> DimensionMovementComponent CharacterMovementComponent
    tools/vtable-diff.py <pid> DimensionMovementComponent CharacterMovementComponent --ile 400
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_common import Pamiec

MODUL_OD = 0x140000000
MODUL_DO = 0x148000000


def znajdz_cdo(m, nazwa_klasy):
    """Wzorzec klasy o tej nazwie. Szukamy po nazwie obiektu `Default__X`,
    bo to jedyna instancja pewna i zawsze obecna."""
    cel = "Default__" + nazwa_klasy
    for _, obj, klasa, _, _ in m.naglowki():
        if not klasa:
            continue
        if m.nazwa_obiektu(obj) == cel:
            return obj
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pid", type=int)
    ap.add_argument("pochodna")
    ap.add_argument("bazowa")
    ap.add_argument("--ile", type=int, default=400, help="ile gniazd porownac")
    a = ap.parse_args()

    m = Pamiec(a.pid)
    m.wykryj_superstruct()

    cdo_p = znajdz_cdo(m, a.pochodna)
    cdo_b = znajdz_cdo(m, a.bazowa)
    if not cdo_p or not cdo_b:
        print(f"nie znalazlem wzorca klasy: "
              f"{a.pochodna if not cdo_p else a.bazowa}", file=sys.stderr)
        return 1

    vt_p = m.wskaznik(cdo_p)
    vt_b = m.wskaznik(cdo_b)
    print(f"{a.pochodna}: CDO {hex(cdo_p)}  vtable {hex(vt_p)}")
    print(f"{a.bazowa}: CDO {hex(cdo_b)}  vtable {hex(vt_b)}")

    rozne = []
    for i in range(a.ile):
        p = m.wskaznik(vt_p + i * 8)
        b = m.wskaznik(vt_b + i * 8)
        if p is None or b is None:
            break
        if not (MODUL_OD <= p < MODUL_DO) or not (MODUL_OD <= b < MODUL_DO):
            break
        if p != b:
            rozne.append((i, p, b))

    print(f"\nnadpisanych gniazd: {len(rozne)}")
    for i, p, b in rozne:
        print(f"  gniazdo {i:3d}   gra 0x{p:X}   silnik 0x{b:X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
