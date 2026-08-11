#!/usr/bin/env python3
"""Kto ma ekwipunek i jaka rola ma jego wlasciciel — sonda do problemu broni.

Po co powstala
--------------
DLL klienta szuka komponentu ekwipunku, ktorego wlasciciel ma `Role == 2`
(AutonomousProxy), i na drodze B nie znajduje go ani razu: log konczy sie
`BRON: poddaje sie po 40 probach`. Samo „nie znalazlem" nie mowi, KTORY
z warunkow zawiodl — a kandydatow jest kilka:

  * komponent ma klase POCHODNA (`BP..._C`), wiec porownanie nazwy klasy
    wprost do "DimensionInventoryComponent" nie trafia w nic,
  * wlasciciel nie jest pierwszym Outerem,
  * postac klienta ma w tej chwili inna role niz 2,
  * offset `Role` jest inny, niz zakladamy.

To narzedzie rozdziela te przypadki: wypisuje KAZDY komponent ekwipunku
(po DZIEDZICZENIU, nie po nazwie klasy) razem z lancuchem Outer, rola
wlasciciela i biezacym indeksem broni. Uruchamiane na kliencie i na hoscie
daje probke i probke kontrolna z jednego polecenia.

Uzycie:
    tools/bron-lokalna.py <pid> [--baza DimensionInventoryComponent]
    tools/bron-lokalna.py <pid> --role      # sam przeglad rol aktorow-postaci
"""
import argparse
import sys

from ue_common import Pamiec, UOBJ_OUTER_OFF

# Offsety potwierdzone refleksja (`ue-props.py --sprawdz`) i uzywane tez
# w naszej DLL — trzymamy je w JEDNYM miejscu obok siebie, zeby rozjazd
# miedzy sonda a latka byl widoczny od razu.
ACTOR_ROLE_OFF = 0xF0
INV_CURRENT_WEAPON_OFF = 0x148

# Widok pierwszoosobowy. Potrzebny, bo objaw „hostowi znika bron" okazal sie
# szerszy: znika CALY zestaw pierwszoosobowy, rece razem z bronia, przy
# poprawnym liczniku amunicji. Sam `CurrentWeaponIndex` tego nie lapie — zostal
# na `0` przez caly przebieg, w ktorym broni nie bylo widac.
CHAR_MESH1P_OFF = 0x958            # DimensionCharacter::Mesh1P
SCENECOMP_VISIBLE_OFF = 0x14C      # bVisible
SCENECOMP_HIDDEN_OFF  = 0x14D      # bHiddenInGame
SCENECOMP_ATTACH_OFF  = 0x0C0      # AttachParent

ROLE_NAZWY = {0: "None", 1: "SimulatedProxy", 2: "AutonomousProxy", 3: "Authority"}


def opis_roli(v):
    if v is None:
        return "?"
    return f"{v} ({ROLE_NAZWY.get(v, 'poza zakresem')})"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pid", type=int)
    ap.add_argument("--baza", default="DimensionInventoryComponent",
                    help="klasa bazowa szukanych komponentow")
    ap.add_argument("--role", action="store_true",
                    help="dodatkowo przeglad rol wszystkich aktorow-postaci")
    ap.add_argument("--role-off", type=lambda s: int(s, 0), default=ACTOR_ROLE_OFF,
                    help="offset pola Role w aktorze (domyslnie 0xF0)")
    ap.add_argument("--zwiezle", action="store_true",
                    help="jeden wiersz na REALNY komponent — do szeregu czasowego")
    a = ap.parse_args()

    m = Pamiec(a.pid)
    off = m.wykryj_superstruct()
    if off is None:
        print("nie udalo sie wykryc SuperStruct — zly pid albo gra jeszcze wstaje",
              file=sys.stderr)
        return 1
    if not a.zwiezle:
        print(f"pid={a.pid}  SuperStruct@{hex(off)}  Role@{hex(a.role_off)}")

    # Nazwy klas rozwiazujemy raz na KLASE, nie na obiekt: klas sa tysiace,
    # obiektow setki tysiecy. Bez tego przejscie trwa minuty i przestaje byc
    # migawka jednej chwili.
    pasujace_klasy = {}
    znalezione = []
    for _, obj, klasa, _, _ in m.naglowki():
        if not klasa:
            continue
        ok = pasujace_klasy.get(klasa)
        if ok is None:
            ok = any(m.nazwa_obiektu(k).lower() == a.baza.lower()
                     for k in m.lancuch_klas(klasa))
            pasujace_klasy[klasa] = ok
        if ok:
            znalezione.append((obj, klasa))

    if a.zwiezle:
        # Jeden wiersz na REALNY komponent (bez wzorcow klas). Format staly,
        # zeby dalo sie go czytac jako szereg czasowy i puscic przez `diff`.
        import time
        znacznik = time.strftime("%H:%M:%S")
        realne = 0
        for obj, klasa in znalezione:
            wl = m.wskaznik(obj + UOBJ_OUTER_OFF)
            if not wl:
                continue
            nazwa_wl = m.nazwa_obiektu(wl)
            if nazwa_wl.startswith("Default__") or \
               m.nazwa_obiektu(obj).startswith("Default__"):
                continue
            realne += 1
            # Stan widoku pierwszoosobowego dopisujemy do tego samego wiersza,
            # zeby w szeregu czasowym bylo widac CHWILE, w ktorej rece znikaja.
            # UWAGA: 0x14C i 0x14D to POLA BITOWE USceneComponent, nie bool-e.
            # Wypisujemy je surowo (szesnastkowo) i celowo ich nie tlumaczymy —
            # w szeregu czasowym liczy sie ZMIANA bajtu, a rozpisywanie bitow
            # bez potwierdzenia maski byloby zgadywaniem. Zmierzone wartosci:
            # 0x63 dla postaci ogladanej lokalnie, 0x43 dla zdalnej kopii.
            mesh = m.wskaznik(wl + CHAR_MESH1P_OFF)
            if mesh:
                widok = (f"Mesh1P[bity=0x{m.u8(mesh + SCENECOMP_VISIBLE_OFF):02X}"
                         f"/0x{m.u8(mesh + SCENECOMP_HIDDEN_OFF):02X}"
                         f" attach={'jest' if m.wskaznik(mesh + SCENECOMP_ATTACH_OFF) else 'BRAK'}]")
            else:
                widok = "Mesh1P[BRAK]"
            print(f"{znacznik} pid={a.pid} {nazwa_wl} "
                  f"Role={opis_roli(m.u8(wl + a.role_off))} "
                  f"idx={m.i32(obj + INV_CURRENT_WEAPON_OFF)} {widok}")
        if realne == 0:
            print(f"{znacznik} pid={a.pid} BRAK realnych komponentow ekwipunku")
        return 0

    print(f"\nkomponentow dziedziczacych po {a.baza}: {len(znalezione)}")
    for obj, klasa in znalezione:
        wl = m.wskaznik(obj + UOBJ_OUTER_OFF)
        nazwa_wl = m.nazwa_obiektu(wl) if wl else "-"
        klasa_wl = m.nazwa_klasy(wl) if wl else "-"
        rola = m.u8(wl + a.role_off) if wl else None
        idx = m.i32(obj + INV_CURRENT_WEAPON_OFF)
        cdo = nazwa_wl.startswith("Default__") or m.nazwa_obiektu(obj).startswith("Default__")
        print(f"  {hex(obj)} klasa={m.nazwa_obiektu(klasa)}")
        print(f"      Outer={hex(wl) if wl else '-'} {nazwa_wl} ({klasa_wl})"
              f"{'  [WZORZEC KLASY]' if cdo else ''}")
        print(f"      Role={opis_roli(rola)}   CurrentWeaponIndex={idx}")
        print(f"      sciezka={m.sciezka(obj)}")

    if a.role:
        # Probka kontrolna dla samego odczytu roli: jesli offset jest dobry,
        # wartosci ukladaja sie w 0..3, a nie w przypadkowe bajty.
        print("\n── role aktorow dziedziczacych po Pawn ──")
        widziane = {}
        for _, obj, klasa, _, _ in m.naglowki():
            if not klasa:
                continue
            ok = widziane.get(klasa)
            if ok is None:
                ok = any(m.nazwa_obiektu(k) == "Pawn" for k in m.lancuch_klas(klasa))
                widziane[klasa] = ok
            if not ok:
                continue
            n = m.nazwa_obiektu(obj)
            if n.startswith("Default__"):
                continue
            print(f"  {hex(obj)} {n} ({m.nazwa_obiektu(klasa)})"
                  f"  Role={opis_roli(m.u8(obj + a.role_off))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
