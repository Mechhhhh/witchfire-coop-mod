#!/usr/bin/env python3
"""Szereg czasowy `Acceleration`, `Velocity` i znacznika wejscia ruchu.

Po co
-----
Pojedynczy odczyt z zewnatrz trafia w przypadkowa chwile i mowi „nic sie nie
dzieje" — co wyglada jak wynik, a nim nie jest (zasada 6). Ale sprawdzenie
„czy wyzwalacz latki KIEDYKOLWIEK ma szanse zadzialac" nie wymaga trafienia
w chwile objawu: wystarczy PRZEBIEG wartosci przez kilkadziesiat sekund.

Ten skrypt odpowiada dokladnie na to pytanie i rozroznia dwie ciszy, ktore
w logu wygladaja identycznie:
  - `Acceleration` stoi na zerze przez caly czas  -> wyzwalacz jest zly,
  - `Acceleration` bywa niezerowe                 -> wyzwalacz jest dobry,
    a stempel nie dochodzi z INNEGO powodu.

Uzycie
------
  tools/probka-ruchu.py <pid> <adres-komponentu-ruchu> [sekundy]
  tools/probka-ruchu.py 75171 0x53A4B380 40
"""
import struct
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from ue_common import Pamiec  # noqa: E402

COMP_PRZYSPIESZENIE = 0x22C
COMP_PREDKOSC       = 0x0C4
COMP_POSTAC         = 0x130
PIONEK_ZNACZNIK     = 0xC74
CHAR_STATE_MACHINE  = 0x968
SM_CURRENT_IDX      = 0x178
KOMP_SWIAT          = 0x0A8
SWIAT_CZAS          = 0x5A0


def wek(p, adres):
    b = p.czytaj(adres, 12)
    if not b or len(b) < 12:
        return None
    return struct.unpack("<fff", b)


def dlugosc(v):
    return (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5 if v else -1.0


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    pid = int(sys.argv[1])
    comp = int(sys.argv[2], 16)
    sek = int(sys.argv[3]) if len(sys.argv) > 3 else 30

    # Bufor stron musi byc WYLACZONY: probkujemy zmieniajace sie wartosci,
    # a buforowana strona pokazywalaby w kolko pierwszy odczyt.
    p = Pamiec(pid, buforuj=False)

    postac = struct.unpack("<Q", p.czytaj(comp + COMP_POSTAC, 8))[0]
    sm = struct.unpack("<Q", p.czytaj(postac + CHAR_STATE_MACHINE, 8))[0]
    print(f"komponent 0x{comp:X}  postac 0x{postac:X}  maszyna 0x{sm:X}")
    print(f"{'czas':>6}  {'|przysp|':>9}  {'|predk|':>9}  {'znacznik':>10}  "
          f"{'zegar':>9}  {'wiek':>7}  stan")

    t0 = time.time()
    maks_a = maks_v = 0.0
    ile_a = 0
    n = 0
    while time.time() - t0 < sek:
        a = dlugosc(wek(p, comp + COMP_PRZYSPIESZENIE))
        v = dlugosc(wek(p, comp + COMP_PREDKOSC))
        zn = struct.unpack("<f", p.czytaj(postac + PIONEK_ZNACZNIK, 4))[0]
        swiat_b = p.czytaj(sm + KOMP_SWIAT, 8)
        swiat = struct.unpack("<Q", swiat_b)[0] if swiat_b else 0
        zegar = -1.0
        if swiat > 0x10000:
            cb = p.czytaj(swiat + SWIAT_CZAS, 4)
            if cb:
                zegar = struct.unpack("<f", cb)[0]
        stan_b = p.czytaj(sm + SM_CURRENT_IDX, 4)
        stan = struct.unpack("<i", stan_b)[0] if stan_b else -1

        maks_a = max(maks_a, a)
        maks_v = max(maks_v, v)
        if a > 1.0:
            ile_a += 1
        n += 1
        print(f"{time.time() - t0:6.1f}  {a:9.1f}  {v:9.1f}  {zn:10.3f}  "
              f"{zegar:9.1f}  {zegar - zn:7.2f}  {stan}")
        time.sleep(0.25)

    print()
    print(f"probek: {n}   |przysp| niezerowe w {ile_a} ({100 * ile_a / max(n, 1):.0f}%)   "
          f"maks przysp {maks_a:.1f}   maks predkosc {maks_v:.1f}")
    if ile_a == 0:
        print("WNIOSEK: przyspieszenie NIGDY nie bylo niezerowe w tym oknie — albo gracz "
              "sie nie ruszal, albo serwer go nie rozpakowuje. Powtorzyc, gdy gracz idzie.")
    else:
        print("WNIOSEK: przyspieszenie BYWA niezerowe — wyzwalacz `fix_czas` ma na czym stac.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
