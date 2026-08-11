#!/usr/bin/env python3
"""Kto ustawia KTORY warunek maszyny stanow — bez dzialajacej gry.

Po co
-----
Pytanie „ktora funkcja liczy `HasMovementInput`" rozwiazywalismy dotad przez
wypisanie listy wolajacych `UpdateCustomConditionBool` i sprawdzanie ich
pojedynczo. To kosztowalo dzien i skonczylo sie lista czterech kandydatow,
z ktorych ZADEN nie byl szukana funkcja (11.08 — wszystkie cztery to
`RunToggled` albo warunki broni).

Ten skrypt odpowiada od razu na cale pytanie: dla KAZDEGO miejsca wywolania
podaje nazwe znacznika, ktory tam leci. Dziala, bo gra buduje znacznik tuz
przed wywolaniem, ze zwyklego literalu:

    lea  rdx, [rip + X]      ; "State.Condition.Weapon.AutoReloadEnabled"
    call 0x141ED4040         ; FString/FName z literalu
    call 0x1434D5510         ; RequestGameplayTag
    ...
    call 0x14180A350         ; UpdateCustomConditionBool(this, tag, bool)

Wiec „ostatni literal `State.*` przed wywolaniem, w tej samej funkcji" JEST
nazwa warunku. Tam gdzie nie jest — skrypt mowi `?` zamiast zgadywac.

Uzycie
------
  tools/warunki.py 0x14180A350            # kto ustawia co
  tools/warunki.py 0x14180A350 --szukaj HasMovementInput
  tools/warunki.py 0x14180A350 --pelne    # z adresami literalow
"""
import argparse
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from obraz import RIP, Obraz, literal, md  # noqa: E402


def fragmenty(ob, gr):
    """Wszystkie kawalki funkcji, nie tylko wpis trafiony w .pdata.

    MSVC tnie funkcje na kawalki i kazdy dostaje wlasny wpis RUNTIME_FUNCTION;
    wpis „glowny" bywa 40-bajtowym prologiem, a cialo lezy w kawalkach obok.
    Skan wylacznie po trafionym wpisie gubil 17 z 34 wywolan — kazde wygladalo
    wtedy na „brak literalu", co jest dokladnie tym rodzajem ciszy, ktora
    w tym projekcie dwa razy przeczytano jako wynik negatywny.
    """
    poczatek, koniec = gr
    zakresy = {gr}
    for p, k, u in ob._wczytaj_pdata():
        rodzic = ob._rodzic(u)
        if rodzic == gr or (poczatek <= p < koniec):
            zakresy.add((p, k))
    return sorted(zakresy)


def literaly_funkcji(ob, gr):
    """[(adres_instrukcji, cel, napis)] dla calej funkcji, w kolejnosci adresow.

    Czytamy kawalki w calosci (a nie do pierwszego `ret`), bo MSVC wplata
    w srodek bloki `ret` z wczesnych wyjsc — zatrzymanie sie na pierwszym
    gubi wiekszosc tresci.
    """
    wynik = []
    wywolania = []
    for poczatek, koniec in fragmenty(ob, gr):
        dane = ob.czytaj(poczatek, koniec - poczatek)
        for i in md().disasm(dane, poczatek):
            m = RIP.search(i.op_str)
            if m and i.mnemonic in ("lea", "mov"):
                cel = i.address + i.size + int(m.group(1), 16)
                lit = literal(ob, cel)
                if lit:
                    wynik.append((i.address, cel, lit))
            if i.mnemonic == "call" and i.op_str.startswith("0x"):
                wywolania.append((i.address, int(i.op_str, 16)))
    wynik.sort()
    wywolania.sort()
    return wynik, wywolania


def main():
    p = argparse.ArgumentParser()
    p.add_argument("adres", help="funkcja aktualizujaca warunek, np. 0x14180A350")
    p.add_argument("--szukaj", help="pokaz tylko funkcje z tym napisem w warunku")
    p.add_argument("--przedrostek", default="State.",
                   help="jakie literaly liczyc za nazwe warunku (domyslnie 'State.')")
    p.add_argument("--pelne", action="store_true", help="wypisz wszystkie literaly funkcji")
    a = p.parse_args()

    cel = int(a.adres, 16)
    ob = Obraz()

    # kto wola — skan `call rel32` po sekcjach wykonywalnych
    wolajacy = []
    for z in ob.wykonywalne():
        dane = ob.dane[z["plik"]:z["plik"] + z["dlugosc"]]
        baza = z["adres"]
        szukane = 0
        while True:
            # E8 = call rel32
            i = dane.find(b"\xe8", szukane)
            if i < 0:
                break
            szukane = i + 1
            if i + 5 > len(dane):
                break
            rel = int.from_bytes(dane[i + 1:i + 5], "little", signed=True)
            if baza + i + 5 + rel == cel:
                wolajacy.append(baza + i)

    print(f"wolajacych: {len(wolajacy)}\n")

    # grupujemy po funkcji nadrzednej
    funkcje = {}
    for w in wolajacy:
        gr = ob.funkcja(w)
        funkcje.setdefault(gr, []).append(w)

    ile_pokazanych = 0
    for gr in sorted(funkcje, key=lambda g: (g is None, g or (0, 0))):
        miejsca = sorted(funkcje[gr])
        if gr is None:
            print(f"  [poza .pdata] {', '.join(f'0x{m:X}' for m in miejsca)}")
            continue
        poczatek, koniec = gr
        lit, _ = literaly_funkcji(ob, gr)
        warunki = [x for x in lit if x[2].startswith(a.przedrostek)]

        pary = []
        for m in miejsca:
            przed = [x for x in warunki if x[0] < m]
            pary.append((m, przed[-1] if przed else None))

        if a.szukaj and not any(pr and a.szukaj.lower() in pr[2].lower() for _, pr in pary):
            continue
        ile_pokazanych += 1

        print(f"── funkcja 0x{poczatek:X}–0x{koniec:X}  ({koniec - poczatek} B, "
              f"{len(miejsca)} wywolan)")
        for m, pr in pary:
            nazwa = pr[2] if pr else "?  (brak literalu State.* przed wywolaniem)"
            print(f"     0x{m:X}  ->  {nazwa}")
        if a.pelne:
            for adr, celu, s in lit:
                print(f"        literal 0x{adr:X} -> 0x{celu:X}  \"{s}\"")
        print()

    if a.szukaj:
        print(f"funkcji pasujacych do '{a.szukaj}': {ile_pokazanych}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
