#!/usr/bin/env python3
"""Kto CZYTA, a kto ZAPISUJE dane pole struktury — bez dzialajacej gry.

Po co
-----
Pulapka sprzetowa (`pulapka-zapisu.py`) odpowiada na to samo pytanie, ale wymaga
dzialajacej gry, zatrzymuje watek i jest ZAKAZANA w trakcie dolaczania klienta.
Tutaj to samo pytanie zadajemy obrazowi: „ktore instrukcje w ogole dotykaja
`[cos + 0xC74]`". Odpowiedz jest pelna (widzi kod, ktory nigdy sie nie wykonal)
i darmowa.

To bylo brakujace ogniwo w sprawie sprintu: warunek `HasMovementInput` liczy sie
ze znacznika czasu pod `pionek+0xC74`, wiec pytanie „dlaczego u klienta jest
zerowy" jest pytaniem „kto go zapisuje i czemu tam nie dochodzi".

Jak to dziala
-------------
Offset siedzi w kodzie jako `disp32` — cztery bajty little-endian w instrukcji.
Zamiast deasemblowac 80 MB liniowo, szukamy tych czterech bajtow (szybko), a potem
deasemblujemy LINIOWO OD POCZATKU FUNKCJI, w ktorej trafienie lezy (granice z
.pdata), i bierzemy te instrukcje, ktora te bajty pokrywa.

Dlaczego nie prosciej, przez cofanie sie po bajcie: bo to klamie. Pierwsza wersja
tego skryptu tak wlasnie robila i odczyt `movss xmm0, [rcx+0xC74]` pod 0x141871230
zobaczyla jako `adc byte ptr [rcx+0xC74], al` pod 0x141871232 — bo dwa bajty dalej
przypadkiem zaczyna sie poprawna, ale nieprawdziwa instrukcja. Granica instrukcji
nie jest lokalnie rozpoznawalna; trzeba ja wyprowadzic z punktu, o ktorym wiadomo,
ze jest granica.

Uzycie
------
  tools/pole.py 0xC74                 # wszystko, co dotyka +0xC74
  tools/pole.py 0xC74 --zapis         # tylko zapisy
  tools/pole.py 0xC74 --baza rdi      # tylko przez konkretny rejestr
  tools/pole.py 0xC74 --funkcje       # zgrupowane po funkcji nadrzednej
"""
import argparse
import struct
import sys

import capstone

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from obraz import Obraz, literal  # noqa: E402

REJESTRY = {}


def czy_zapis(i):
    """Czy instrukcja ZAPISUJE do operandu pamieciowego.

    Capstone nie mowi tego wprost, wiec patrzymy na pierwszy operand: w skladni
    Intela cel jest pierwszy. Instrukcje czytajaco-zapisujace (add, or, inc)
    licza sie jako zapis, bo modyfikuja pole.
    """
    if not i.operands:
        return False
    p = i.operands[0]
    if p.type != capstone.x86.X86_OP_MEM:
        return False
    # `cmp` i `test` maja cel-pamiec, ale niczego nie zmieniaja
    return i.mnemonic not in ("cmp", "test", "push", "bt")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("offset", help="offset pola, np. 0xC74")
    p.add_argument("--zapis", action="store_true", help="tylko zapisy")
    p.add_argument("--odczyt", action="store_true", help="tylko odczyty")
    p.add_argument("--baza", help="tylko przez ten rejestr bazowy, np. rdi")
    p.add_argument("--funkcje", action="store_true", help="grupuj po funkcji nadrzednej")
    p.add_argument("--kontekst", type=int, default=0, help="ile instrukcji przed/po pokazac")
    a = p.parse_args()

    off = int(a.offset, 16) if a.offset.lower().startswith("0x") else int(a.offset)
    if off < 0x80:
        print("UWAGA: maly offset koduje sie jako disp8, nie disp32 — ten skrypt go nie "
              "znajdzie. Dziala od 0x80 w gore.", file=sys.stderr)
    wzor = struct.pack("<i", off)

    ob = Obraz()
    m = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    m.detail = True

    import bisect
    tab = ob._wczytaj_pdata()
    poczatki = [t[0] for t in tab]
    pamiec = {}          # (poczatek, koniec) -> [instrukcje]

    def kawalek(adres):
        """SUROWY wpis .pdata zawierajacy adres — czyli pewna granica instrukcji.

        Celowo NIE rozwiazujemy tu fragmentu do funkcji glownej (jak robi
        `ob.funkcja`): do deasemblacji potrzebny jest poczatek TEGO kawalka,
        bo tylko on jest granica instrukcji. Funkcja glowna sluzy do grupowania.
        """
        i = bisect.bisect_right(poczatki, adres) - 1
        if i < 0:
            return None
        p, k, _u = tab[i]
        return (p, k) if p <= adres < k else None

    def instrukcje(zakres):
        if zakres in pamiec:
            return pamiec[zakres]
        poczatek, koniec = zakres
        lista = list(m.disasm(ob.czytaj(poczatek, koniec - poczatek), poczatek))
        pamiec[zakres] = lista
        return lista

    trafienia = []
    domyslane = set()
    niepewne = 0
    for z in ob.wykonywalne():
        dane = ob.dane[z["plik"]:z["plik"] + z["dlugosc"]]
        baza = z["adres"]
        szukane = 0
        while True:
            i = dane.find(wzor, szukane)
            if i < 0:
                break
            szukane = i + 1
            adres_disp = baza + i

            zakres = kawalek(adres_disp)
            ins = None
            if zakres is not None:
                for kandydat in instrukcje(zakres):
                    if kandydat.address <= adres_disp < kandydat.address + kandydat.size:
                        ins = kandydat
                        break
            if ins is None:
                # Funkcja-lisc bez ramki stosu nie dostaje wpisu w .pdata — a wlasnie
                # taka jest `0x141871230` (dwie instrukcje, sam odczyt pola). Zamiast
                # ja zgubic, dekodujemy wstecz i mowimy wprost, ze granica jest
                # domyslana. Od najdluzszego cofniecia, bo prawdziwa instrukcja ma
                # komplet przedrostkow (`F3 0F 10 ...`), a falszywe zaczynaja sie
                # w srodku i sa krotsze.
                for wstecz in range(15, 0, -1):
                    start = i - wstecz
                    if start < 0:
                        continue
                    try:
                        k = next(m.disasm(dane[start:start + 20], baza + start, 1))
                    except StopIteration:
                        continue
                    if k.address + k.size <= adres_disp:
                        continue
                    if any(o.type == capstone.x86.X86_OP_MEM and o.mem.disp == off
                           for o in k.operands):
                        ins = k
                        break
                if ins is None:
                    niepewne += 1
                    continue
                zakres = (ins.address, ins.address + ins.size)
                domyslane.add(ins.address)
            gr = ob.funkcja(adres_disp) or zakres

            dopasowane = None
            for o in ins.operands:
                if o.type == capstone.x86.X86_OP_MEM and o.mem.disp == off:
                    dopasowane = o
                    break
            if dopasowane is None:
                continue        # cztery bajty to dana albo czesc immediate, nie disp

            rej = ins.reg_name(dopasowane.mem.base) if dopasowane.mem.base else "?"
            if a.baza and rej != a.baza:
                continue
            w = czy_zapis(ins)
            if a.zapis and not w:
                continue
            if a.odczyt and w:
                continue
            trafienia.append((ins.address, rej, w, f"{ins.mnemonic} {ins.op_str}", gr, z))

    print(f"instrukcji dotykajacych +0x{off:X}: {len(trafienia)}"
          f"  (zapisow: {sum(1 for t in trafienia if t[2])}"
          f", pominietych: {niepewne})")
    if domyslane:
        print(f"  * {len(domyslane)} pozycji poza .pdata — granica instrukcji DOMYSLANA "
              f"(funkcje-liscie bez ramki stosu). Sprawdz je przez obraz.py fun.")
    print()

    def wypisz(adres, rej, w, tekst, zakres):
        znak = "ZAPIS " if w else "odczyt"
        gwiazdka = " *" if adres in domyslane else ""
        print(f"     0x{adres:X}  {znak}  [{rej}+0x{off:X}]   {tekst}{gwiazdka}")
        if a.kontekst:
            for ins in instrukcje(kawalek(adres) or zakres):
                if 0 < adres - ins.address <= a.kontekst * 8 or \
                   0 < ins.address - adres <= a.kontekst * 8:
                    print(f"            0x{ins.address:X}  {ins.mnemonic:8s} {ins.op_str}")

    if a.funkcje:
        grupy = {}
        for t in trafienia:
            grupy.setdefault(t[4], []).append(t)
        for gr in sorted(grupy):
            print(f"── funkcja 0x{gr[0]:X}–0x{gr[1]:X}")
            for adres, rej, w, tekst, zakres, _z in sorted(grupy[gr]):
                wypisz(adres, rej, w, tekst, zakres)
            print()
        return 0

    for adres, rej, w, tekst, zakres, _z in sorted(trafienia):
        wypisz(adres, rej, w, tekst, zakres)
    return 0


if __name__ == "__main__":
    sys.exit(main())
