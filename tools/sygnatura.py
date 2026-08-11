#!/usr/bin/env python3
"""Rozpoznaje, CZY TA AWARIA JUZ BYLA — po sygnaturze, nie po wrazeniu.

Po co powstalo
--------------
Dokumentacja rosla liniowo: kazdy przebieg dostawal wlasna sekcje, choc wynik
czesto byl ten sam, co poprzednio. Przy zjawisku niedeterministycznym to zabija
diagnoze, bo najwazniejsze pytanie brzmi „czy to sie POWTARZA, czy jest nowe",
a tego nie widac w scianie tekstu.

Do tego z ekranu awarie wygladaja identycznie — host znika i tyle. Dwa razy
omal nie uznalem dzialajacej latki za nieskuteczna, bo objaw byl ten sam,
a sygnatura zupelnie inna.

Sygnatura = adres odczytu + watek + skrot ze stosu. Narzedzie liczy ja dla
kazdego zrzutu i grupuje przebiegi, ktore mialy TE SAMA awarie.

Uzycie
------
  sygnatura.py                     wszystkie zrzuty obu instancji, pogrupowane
  sygnatura.py --katalog <sciezka> jeden konkretny zrzut
  sygnatura.py --od 14:00          tylko zrzuty po tej godzinie dzisiaj
"""
import argparse
import hashlib
import os
import re
import sys
from collections import defaultdict

# WF_PREFIX_ROOT — katalog, w ktorym leza prefiksy Proton obu instancji
# (ten sam, ktorego uzywa tools/launch-instance2.sh).
KORZEN_PREFIKSOW = os.environ.get(
    "WF_PREFIX_ROOT", os.path.expanduser("~/.local/share/witchfire-mp"))

PREFIKSY = {
    "host":   "compat1",
    "klient": "compat2",
}


def zrzuty(kto):
    baza = os.path.join(
        KORZEN_PREFIKSOW, PREFIKSY[kto],
        "pfx/drive_c/users/steamuser/AppData/Local/Witchfire/Saved/Crashes")
    if not os.path.isdir(baza):
        return []
    out = []
    for d in os.listdir(baza):
        p = os.path.join(baza, d)
        x = os.path.join(p, "CrashContext.runtime-xml")
        if os.path.isfile(x):
            out.append((os.path.getmtime(p), p, x))
    return sorted(out)


def opis(sciezka_xml):
    t = open(sciezka_xml, errors="replace").read()

    def pole(nazwa):
        m = re.search(rf"<{nazwa}>(.*?)</{nazwa}>", t, re.S)
        return m.group(1).strip() if m else ""

    blad = pole("ErrorMessage")
    m = re.search(r"reading address (0x[0-9A-Fa-f]+)", blad)
    adres = m.group(1) if m else "?"
    # numer watku, ktory padl
    watek = ""
    m = re.search(r"<Thread>.*?<IsCrashed>true</IsCrashed>.*?<ThreadName>(.*?)</ThreadName>", t, re.S)
    if m:
        watek = m.group(1)
    else:
        m = re.search(r"<ThreadName>(.*?)</ThreadName>", t)
        watek = m.group(1) if m else "?"
    ramki = re.findall(r"0x([0-9A-Fa-f]{9,16})", t)[:8]
    skrot = hashlib.sha1(("|".join(ramki)).encode()).hexdigest()[:8]
    return {
        "adres": adres,
        "watek": watek,
        "skrot": skrot,
        "ramki": ramki[:4],
        "sekundy": pole("SecondsSinceStart"),
    }


def main():
    ap = argparse.ArgumentParser(description="grupuje awarie po sygnaturze")
    ap.add_argument("--katalog", help="pojedynczy katalog zrzutu")
    ap.add_argument("--od", help="tylko zrzuty po tej godzinie, np. 14:00")
    a = ap.parse_args()

    if a.katalog:
        x = os.path.join(a.katalog, "CrashContext.runtime-xml")
        d = opis(x)
        print(f"adres={d['adres']}  watek={d['watek']}  sygnatura={d['skrot']}")
        return 0

    import datetime
    prog = None
    if a.od:
        h, mi = a.od.split(":")
        dzis = datetime.date.today()
        prog = datetime.datetime.combine(dzis, datetime.time(int(h), int(mi))).timestamp()

    grupy = defaultdict(list)
    for kto in PREFIKSY:
        for mtime, kat, x in zrzuty(kto):
            if prog and mtime < prog:
                continue
            try:
                d = opis(x)
            except Exception:
                continue
            czas = datetime.datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M")
            grupy[(d["adres"], d["watek"], d["skrot"])].append((czas, kto, d))

    if not grupy:
        print("brak zrzutow w zadanym zakresie")
        return 0

    print(f"awarii unikalnych (po sygnaturze): {len(grupy)}\n")
    for (adres, watek, skrot), lista in sorted(grupy.items(), key=lambda x: -len(x[1])):
        print(f"══ adres={adres}  watek={watek}  sygnatura={skrot} ══")
        print(f"   wystapien: {len(lista)}")
        for czas, kto, _d in lista[-6:]:
            print(f"     {czas}  {kto}")
        print(f"   pierwsze ramki: {', '.join('0x'+r for r in lista[-1][2]['ramki'])}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
