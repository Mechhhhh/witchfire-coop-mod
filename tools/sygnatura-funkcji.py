#!/usr/bin/env python3
"""Parametry `UFunction` — czego dana funkcja gry oczekuje na wejściu.

Po co powstało
--------------
`ue-funcs.py` mówi, że funkcja istnieje i gdzie leży jej przejściówka, ale nie
mówi, **co jej podać**. Do wywołania czegokolwiek z naszej biblioteki (albo do
odczytania argumentu w haku) trzeba znać typy, rozmiary i przesunięcia
parametrów — inaczej zostaje zgadywanie, a zgadywanie przy wywołaniu kodu gry
kończy się awarią bez śladu w logu.

Parametry `UFunction` to zwykłe właściwości z flagą `CPF_Parm` w łańcuchu
`ChildProperties`, ułożone dokładnie tak, jak leżą w buforze przekazywanym do
`ProcessEvent`. Zwracana wartość ma dodatkowo `CPF_ReturnParm`.

Użycie
------
  sygnatura-funkcji.py <pid> ServerSetTargeting AddTransitionToQueue ...
  sygnatura-funkcji.py <pid> --klasa DimensionStateMachineComponent
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_common import Pamiec, SS_TO_CHILDPROPERTIES

FF_CLASS = 0x08
FF_NEXT  = 0x20
FF_NAME  = 0x28
FP_ARRAYDIM = 0x38
FP_ELEMSIZE = 0x3C
FP_FLAGS    = 0x40
FP_OFFSET   = 0x4C

CPF_Parm       = 0x00000080
CPF_OutParm    = 0x00000100
CPF_ReturnParm = 0x00000400
CPF_ConstParm  = 0x00000200


def typ(m, prop):
    kl = m.wskaznik(prop + FF_CLASS)
    if not kl:
        return "?"
    d = m.czytaj(kl, 8)
    if not d:
        return "?"
    import struct
    idx, num = struct.unpack("<II", d)
    return m.nazwa_z_para(idx, num)


def nazwa_struktury(m, prop):
    """Dla `StructProperty` — nazwa struktury. Wskaźnik na `UScriptStruct`
    leży zaraz za samym `FProperty` (podtypy dokładają pola na końcu)."""
    s = m.wskaznik(prop + 0x78)
    return m.nazwa_obiektu(s) if s else None


def pola_struktury(m, prop, so):
    """Układ struktury parametru — inaczej nie da się jej zbudować."""
    s = m.wskaznik(prop + 0x78)
    if not s:
        return []
    p = m.wskaznik(s + so + SS_TO_CHILDPROPERTIES)
    wynik, n = [], 0
    while p and n < 64:
        wynik.append((m.i32(p + FP_OFFSET) or 0, typ(m, p).replace("Property", ""),
                      nazwa_pola(m, p), m.i32(p + FP_ELEMSIZE) or 0))
        p = m.wskaznik(p + FF_NEXT)
        n += 1
    return sorted(wynik)


def nazwa_pola(m, prop):
    import struct
    d = m.czytaj(prop + FF_NAME, 8)
    if not d:
        return "?"
    idx, num = struct.unpack("<II", d)
    return m.nazwa_z_para(idx, num)


def parametry(m, fn, so):
    """Lista parametrów funkcji, w kolejności ułożenia w buforze."""
    p = m.wskaznik(fn + so + SS_TO_CHILDPROPERTIES)
    wynik = []
    n = 0
    while p and n < 64:
        flagi = m.u64(p + FP_FLAGS) or 0
        if flagi & CPF_Parm:
            t = typ(m, p).replace("Property", "")
            wpis = {
                "nazwa": nazwa_pola(m, p),
                "typ": t,
                "offset": m.i32(p + FP_OFFSET) or 0,
                "rozmiar": m.i32(p + FP_ELEMSIZE) or 0,
                "zwrot": bool(flagi & CPF_ReturnParm),
                "wyjscie": bool(flagi & CPF_OutParm),
            }
            if t == "Struct":
                wpis["struktura"] = nazwa_struktury(m, p)
                wpis["pola"] = pola_struktury(m, p, so)
            wynik.append(wpis)
        p = m.wskaznik(p + FF_NEXT)
        n += 1
    return wynik


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pid", type=int, nargs="?")
    ap.add_argument("nazwy", nargs="*", help="nazwy funkcji do pokazania")
    ap.add_argument("--klasa", help="pokaż wszystkie funkcje tej klasy")
    a = ap.parse_args()

    pid = a.pid or int(subprocess.run(["pgrep", "-x", "Witchfire-Win64"],
                                      capture_output=True, text=True).stdout.split()[0])
    m = Pamiec(pid)
    so = m.wykryj_superstruct()
    szukane = set(a.nazwy)

    for _, obj, klasa, _, _ in m.naglowki():
        if m.nazwa_obiektu(klasa) != "Function":
            continue
        nz = m.nazwa_obiektu(obj)
        wl = m.wskaznik(obj + 0x20)
        kl = m.nazwa_obiektu(wl) if wl else "?"
        if szukane and nz not in szukane:
            continue
        if a.klasa and kl != a.klasa:
            continue
        par = parametry(m, obj, so)
        rozm = m.u16(obj + so + 0x76) or 0
        ile = m.u8(obj + so + 0x74) or 0
        print(f"\n{kl}::{nz}   parametrow {ile}, bufor {rozm} B")
        if not par:
            print("    (bez parametrow)")
        for p in par:
            znak = "  <- ZWROT" if p["zwrot"] else ("  (wyjscie)" if p["wyjscie"] else "")
            dodatek = f"  [{p['struktura']}]" if p.get("struktura") else ""
            print(f"    +0x{p['offset']:03X}  {p['typ']:14s} {p['nazwa']:28s} {p['rozmiar']:3d} B{znak}{dodatek}")
            for off, t, nz2, rozm2 in p.get("pola", []):
                print(f"          +0x{off:03X}  {t:14s} {nz2:24s} {rozm2:3d} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
