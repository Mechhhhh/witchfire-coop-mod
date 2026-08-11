#!/usr/bin/env python3
"""Czyta obiekty Unreala z ZYWEGO procesu, z zewnatrz, przez /proc/PID/mem.

Po co to powstalo
-----------------
Caly dzien diagnozy szedl "z zewnatrz": logi, zrzuty ekranu, stany watkow.
To wystarczylo, zeby WYKLUCZAC, ale nie zeby zrozumiec. Zeby dowiedziec sie,
co gra naprawde ma w srodku — czy bron istnieje jako obiekt, co ma w sobie
komponent ekwipunku, co zmienia sie przy `Login` drugiego gracza — trzeba
zajrzec do jej obiektow.

Dlaczego z ZEWNATRZ, a nie przez wstrzykniety kod
-------------------------------------------------
1. Dziala na KLIENCIE, gdzie UE4SS zabija gre, a nasza proxy DLL ma ograniczone
   mozliwosci.
2. Dziala na instancji ZAMROZONEJ — nie wymaga, zeby gra cokolwiek wykonala.
   A wlasnie wtedy najbardziej chcemy zajrzec do srodka.
3. Nie moze niczego zepsuc. W tym projekcie wlasna diagnostyka trzy razy
   popsula mierzone zjawisko; czytanie pamieci z zewnatrz jest bierne.

Skad adresy
-----------
UE4SS sam wyszukuje struktury silnika i zapisuje je w swoim logu — stad:
    GUObjectArray     0x146543810
    FName::ToString   0x141EDC9C0
Pule nazw (`FNamePool`) znalazlem, deasemblujac `FName::ToString`: leniwa
inicjalizacja przekazuje ja w `rcx` pod adresem 0x1464EA8C0.

Uklad struktur to standardowy UE 4.27 (gra zglasza 4.27.2). Sam odczyt pamieci
siedzi teraz w `ue_common.py`, wspolnym z `ue-snapshot.py` i `ue-props.py`.

Uzycie
------
  ue-objects.py <pid> --stat                     ile obiektow, czy odczyt dziala
  ue-objects.py <pid> --find Weapon              obiekty, ktorych nazwa zawiera...
  ue-objects.py <pid> --class BPDimensionPlayerCharacter_C
  ue-objects.py <pid> --isa Actor --find Weapon  potomkowie klasy (patrz nizej)
  ue-objects.py <pid> --dump 0x12345678          pojedynczy obiekt: klasa, outer

Po co `--isa`: w tej grze prawie kazdy aktor to blueprint o nazwie klasy
`BPCos_C`, wiec `--class Weapon` nie trafia w nic, mimo ze bronie w swiecie sa.
`--isa` idzie lancuchem dziedziczenia, wiec znajduje je niezaleznie od nazwy.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_common import (Pamiec, GUOBJECTARRAY, OBJOBJECTS_OFF,
                       NUM_ELEMENTS_OFF, NUM_CHUNKS_OFF)


def main():
    ap = argparse.ArgumentParser(description="czytnik obiektow UE z zywego procesu")
    ap.add_argument("pid", type=int)
    ap.add_argument("--stat", action="store_true", help="ile obiektow i czy odczyt dziala")
    ap.add_argument("--find", help="obiekty, ktorych NAZWA zawiera podany tekst")
    ap.add_argument("--class", dest="klasa", help="obiekty danej KLASY")
    ap.add_argument("--isa", help="obiekty dziedziczace po tej klasie (np. Actor)")
    ap.add_argument("--dump", help="jeden obiekt po adresie szesnastkowym")
    ap.add_argument("--limit", type=int, default=40)
    a = ap.parse_args()

    m = Pamiec(a.pid)

    if a.dump:
        o = int(a.dump, 16)
        print(f"obiekt   0x{o:X}")
        print(f"  nazwa  {m.nazwa_obiektu(o)}")
        print(f"  klasa  {m.nazwa_klasy(o)}")
        print(f"  sciezka {m.sciezka(o)}")
        lancuch = [m.nazwa_obiektu(k) for k in m.lancuch_klas(m.wsk_klasy(o))]
        if lancuch:
            print(f"  rodowod {' <- '.join(lancuch)}")
        return 0

    if a.stat:
        chunks, ile, n_chunk = m.naglowek_tablicy()
        print(f"GUObjectArray  0x{GUOBJECTARRAY:X}")
        print(f"  chunki      0x{chunks or 0:X}")
        print(f"  obiektow    {ile}")
        print(f"  chunkow     {n_chunk}")
        # kontrola poprawnosci: pierwsze obiekty w UE to zawsze klasy silnika
        print("  pierwsze obiekty (kontrola, czy uklad struktur sie zgadza):")
        for n, (idx, o) in enumerate(m.obiekty()):
            print(f"    [{idx}] 0x{o:X}  {m.nazwa_klasy(o):28s} {m.nazwa_obiektu(o)}")
            if n >= 6:
                break
        off = m.wykryj_superstruct()
        print(f"  SuperStruct {'0x%X' % off if off else 'NIE WYKRYTO'} "
              f"(potrzebny do --isa i do ue-props.py)")
        return 0

    igla = (a.find or a.klasa or "").lower()
    if not igla and not a.isa:
        print("podaj --stat, --find, --class, --isa albo --dump")
        return 1

    ile = 0
    for idx, o in m.obiekty():
        if igla:
            pole = m.nazwa_klasy(o) if a.klasa else m.nazwa_obiektu(o)
            if igla not in pole.lower():
                continue
        if a.isa and not m.dziedziczy_po(o, a.isa):
            continue
        print(f"[{idx:6d}] 0x{o:X}  {m.nazwa_klasy(o):30s} {m.sciezka(o)}")
        ile += 1
        if ile >= a.limit:
            print(f"... (przerwano na {a.limit}, uzyj --limit)")
            break
    if ile == 0:
        print("nic nie znaleziono")
    return 0


if __name__ == "__main__":
    sys.exit(main())
